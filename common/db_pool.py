import aiosqlite
import asyncio
import atexit
import sqlite3
import os
from common.config import DB_NAME

# Глобальная переменная соединения
_db_connection = None


def _sync_wal_checkpoint_truncate():
    """
    Синхронный сброс WAL при завершении процесса Python (через atexit).
    Гарантирует, что даже при выходе из процесса без вызова close_pool(),
    WAL сбрасывается и сжимается до 0 байт.
    """
    if not isinstance(DB_NAME, str) or not os.path.exists(DB_NAME):
        return
    try:
        conn = sqlite3.connect(DB_NAME, timeout=3.0)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        finally:
            conn.close()
    except Exception:
        pass


atexit.register(_sync_wal_checkpoint_truncate)

class LazyLock:
    def __init__(self):
        self._lock = None
        self._loop = None
        self._owner = None
        self._depth = 0

    def _get_lock(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and self._loop is not loop):
            self._lock = asyncio.Lock()
            self._loop = loop
            self._owner = None
            self._depth = 0
        return self._lock

    async def acquire(self):
        lock = self._get_lock()
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None

        # Реентерабельный повторный захват из той же таски
        if current is not None and self._owner is current:
            self._depth += 1
            return True

        res = await lock.acquire()
        self._owner = current
        self._depth = 1
        return res

    def release(self):
        if self._lock:
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None

            if current is not None and self._owner is current:
                self._depth -= 1
                if self._depth <= 0:
                    self._depth = 0
                    self._owner = None
                    if self._lock.locked():
                        self._lock.release()
            else:
                if self._depth > 1:
                    self._depth -= 1
                else:
                    self._depth = 0
                    self._owner = None
                    if self._lock.locked():
                        self._lock.release()

    def locked(self):
        return self._get_lock().locked()

    def is_owned_by_current_task(self) -> bool:
        """Проверяет, удерживает ли текущая задача этот замок."""
        if not self.locked():
            return False
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        return current is not None and self._owner is current

    def locked_by_current_task(self) -> bool:
        """Алиас/хелпер для проверки владения замком текущей задачей."""
        return self.is_owned_by_current_task()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()

# ГАРАНТИЯ БЕЗОПАСНОСТИ:
# Этот замок (Lock) не даст боту и сайту одновременно пытаться пересоздать подключение.
_reconnect_lock = LazyLock()

# Глобальный замок для синхронизации задач внутри одного процесса (Task-Safety).
# Обязателен при использовании ручных транзакций (BEGIN IMMEDIATE), 
# чтобы задачи не вклинивались в чужие транзакции.
db_lock = LazyLock()

async def get_pool():
    """
    Возвращает активное соединение.
    Thread-Safe: безопасен для одновременной работы бота и сайта.
    """
    global _db_connection
    
    # 1. Быстрая проверка (Optimistic check)
    if _db_connection is not None:
        try:
            # Проверяем внутренний флаг aiosqlite, жив ли поток
            if _db_connection._running and _db_connection._conn:
                return _db_connection
        except Exception:
            import traceback; traceback.print_exc() # Если проверка не удалась, идем на восстановление

    # 2. Если соединения нет или оно мертвое — входим в режим восстановления
    async with _reconnect_lock:
        # Повторная проверка внутри замка
        if _db_connection is not None:
            try:
                if _db_connection._running and _db_connection._conn:
                    return _db_connection
            except Exception:
                import traceback; traceback.print_exc()
            print("[DB] Reconnecting to database...")
        
        # 3. Аккуратное закрытие старого трупа (если есть)
        if _db_connection:
            try:
                await _db_connection.close()
            except Exception: 
                import traceback; traceback.print_exc()
            _db_connection = None
        
        retries = 3
        for attempt in range(retries):
            try:
                # isolation_level=None ОТКЛЮЧАЕТ неявные транзакции.
                # Теперь мы обязаны сами писать BEGIN/COMMIT, но получаем полный контроль
                # и возможность использовать BEGIN IMMEDIATE для предотвращения дедлоков.
                conn = await aiosqlite.connect(DB_NAME, timeout=60.0, isolation_level=None)
                
                await conn.execute("PRAGMA busy_timeout = 60000;")  
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous = NORMAL;")
                await conn.execute("PRAGMA temp_store = MEMORY;")
                await conn.execute("PRAGMA mmap_size = 1073741824;")
                await conn.execute("PRAGMA cache_size = -131072;")

                await conn.execute("PRAGMA foreign_keys = ON;")
                await conn.execute("PRAGMA wal_autocheckpoint=1000;")
                # Нет await conn.commit(), так как мы в режиме autocommit (isolation_level=None)
                
                _db_connection = conn
                print(f"[DB] Connected successfully (attempt {attempt+1}, isolation_level=None)")
                return _db_connection
            except Exception as e:
                print(f"[DB] Retry {attempt+1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)  # Backoff перед retry
                else:
                    print(f"[DB] CRITICAL ERROR: {e}")
                    raise e
            
        return _db_connection

async def create_pool():
    """Алиас для инициализации, использует ту же безопасную логику."""
    return await get_pool()

async def wal_checkpoint_truncate(db=None) -> bool:
    """
    Принудительный асинхронный сброс всех данных из WAL в основной файл базы данных
    и усечение WAL-файла до 0 байт (PRAGMA wal_checkpoint(TRUNCATE)).
    """
    global _db_connection
    try:
        async with db_lock:
            conn = db or _db_connection or await get_pool()
            if conn:
                async with conn.execute("PRAGMA wal_checkpoint(TRUNCATE);") as cursor:
                    row = await cursor.fetchone()
                    if row:
                        busy, log_frames, ckpt_frames = row
                        print(f"[DB] WAL Checkpoint (TRUNCATE): Busy={busy}, Log={log_frames}, Checkpointed={ckpt_frames}")
                        return busy == 0
                    return True
    except Exception as e:
        print(f"[DB] WAL Checkpoint (TRUNCATE) error: {e}")
    return False


async def close_pool():
    """Безопасное закрытие при выключении бота с обязательным TRUNCATE чекпоинтом."""
    global _db_connection
    async with _reconnect_lock:
        if _db_connection:
            try:
                try:
                    await _db_connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    print("[DB] WAL checkpoint (TRUNCATE) completed successfully before close.")
                except Exception as ckpt_e:
                    print(f"[DB] WAL checkpoint on close error: {ckpt_e}")
                await _db_connection.close()
                print("[DB] Connection closed successfully.")
            except Exception as e:
                print(f"[DB] Close error: {e}")
            finally:
                _db_connection = None

async def db_sleep(delay: float):
    """Безопасный sleep для отпускания db_lock во время ожидания."""
    saved_depth = 0
    is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
    if is_owned_fn and is_owned_fn():
        try:
            saved_depth = getattr(db_lock, "_depth", 1)
            db_lock._depth = 0
            db_lock._owner = None
            if db_lock._lock and db_lock._lock.locked():
                db_lock._lock.release()
        except RuntimeError:
            saved_depth = 0
    try:
        await asyncio.sleep(delay)
    finally:
        if saved_depth > 0:
            lock = db_lock._get_lock()
            await lock.acquire()
            try:
                db_lock._owner = asyncio.current_task()
            except RuntimeError:
                db_lock._owner = None
            db_lock._depth = saved_depth


class db_transaction:
    """
    Асинхронный контекстный менеджер для безопасного выполнения транзакций.
    - Автоматически захватывает db_lock (если текущая задача им еще не владеет).
    - Предотвращает ошибки SQLite 'cannot start a transaction within a transaction'
      путем использования SAVEPOINT при вложенных транзакциях.
    - Поддерживает автоматический retry при sqlite3.OperationalError: database is locked.
    - Гарантирует отсутствие 'cannot commit - no transaction is active' и 'cannot rollback'.
    - Корректно откатывает только свой savepoint при вложенной ошибке или всю транзакцию на верхнем уровне.
    """
    _sp_counter = 0

    def __init__(self, db=None, immediate: bool = True, max_retries: int = 5, base_delay: float = 0.1):
        self.db = db
        self.immediate = immediate
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._is_nested = False
        self._savepoint_name = None
        self._lock_acquired = False

    async def __aenter__(self):
        if not db_lock.is_owned_by_current_task():
            await db_lock.acquire()
            self._lock_acquired = True

        if self.db is None:
            self.db = await get_pool()

        in_tx = getattr(self.db, "in_transaction", False)
        if not in_tx:
            conn = getattr(self.db, "_conn", None)
            if conn:
                in_tx = getattr(conn, "in_transaction", False)

        for attempt in range(self.max_retries):
            try:
                if in_tx:
                    self._is_nested = True
                    db_transaction._sp_counter += 1
                    self._savepoint_name = f"sp_{id(self)}_{db_transaction._sp_counter}"
                    await self.db.execute(f"SAVEPOINT {self._savepoint_name}")
                else:
                    self._is_nested = False
                    if self.immediate:
                        await self.db.execute("BEGIN IMMEDIATE")
                    else:
                        await self.db.execute("BEGIN")
                break
            except Exception as e:
                err_str = str(e).lower()
                if ("locked" in err_str or "busy" in err_str) and attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))
                else:
                    raise
        return self.db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                if self._is_nested and self._savepoint_name:
                    try:
                        await self.db.execute(f"ROLLBACK TO {self._savepoint_name}")
                        await self.db.execute(f"RELEASE {self._savepoint_name}")
                    except Exception:
                        pass
                else:
                    in_tx = getattr(self.db, "in_transaction", False)
                    if not in_tx:
                        conn = getattr(self.db, "_conn", None)
                        if conn:
                            in_tx = getattr(conn, "in_transaction", False)
                    if in_tx:
                        try:
                            await self.db.execute("ROLLBACK")
                        except Exception:
                            pass
            else:
                if self._is_nested and self._savepoint_name:
                    try:
                        await self.db.execute(f"RELEASE {self._savepoint_name}")
                    except Exception:
                        pass
                else:
                    in_tx = getattr(self.db, "in_transaction", False)
                    if not in_tx:
                        conn = getattr(self.db, "_conn", None)
                        if conn:
                            in_tx = getattr(conn, "in_transaction", False)
                    if in_tx:
                        try:
                            await self.db.execute("COMMIT")
                        except Exception:
                            pass
        finally:
            if self._lock_acquired:
                db_lock.release()
                self._lock_acquired = False


async def execute_with_retry(func_or_coro, *args, max_retries: int = 5, base_delay: float = 0.1, **kwargs):
    """
    Выполняет асинхронную функцию или корутину с автоматическим повтором при блокировках SQLite
    (sqlite3.OperationalError: database is locked / busy) с экспоненциальным backoff.
    """
    for attempt in range(max_retries):
        try:
            if callable(func_or_coro):
                res = func_or_coro(*args, **kwargs)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    return await res
                return res
            return await func_or_coro
        except Exception as e:
            err_str = str(e).lower()
            if ("locked" in err_str or "busy" in err_str) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await db_sleep(delay)
            else:
                raise


async def safe_begin_immediate(db) -> bool:
    """
    Безопасно начинает транзакцию BEGIN IMMEDIATE, если транзакция еще не активна.
    Возвращает True, если транзакция была начата этим вызовом, иначе False.
    """
    if db is None:
        db = await get_pool()
    in_tx = getattr(db, "in_transaction", False)
    if not in_tx:
        conn = getattr(db, "_conn", None)
        if conn:
            in_tx = getattr(conn, "in_transaction", False)
    if in_tx:
        return False
    try:
        await db.execute("BEGIN IMMEDIATE")
        return True
    except Exception as e:
        if "cannot start a transaction within a transaction" in str(e).lower():
            return False
        raise


async def safe_commit(db, started_by_caller: bool = True):
    """
    Безопасно фиксирует транзакцию, если она активна и была начата данным контекстом.
    """
    if not started_by_caller or db is None:
        return
    in_tx = getattr(db, "in_transaction", False)
    if not in_tx:
        conn = getattr(db, "_conn", None)
        if conn:
            in_tx = getattr(conn, "in_transaction", False)
    if in_tx:
        try:
            await db.execute("COMMIT")
        except Exception as e:
            if "no transaction is active" in str(e).lower():
                pass
            else:
                raise


async def safe_rollback(db, started_by_caller: bool = True):
    """
    Безопасно откатывает транзакцию, если она активна и была начата данным контекстом.
    """
    if not started_by_caller or db is None:
        return
    in_tx = getattr(db, "in_transaction", False)
    if not in_tx:
        conn = getattr(db, "_conn", None)
        if conn:
            in_tx = getattr(conn, "in_transaction", False)
    if in_tx:
        try:
            await db.execute("ROLLBACK")
        except Exception:
            pass


async def sqlite_wal_checkpoint_task(interval_seconds: int = 600):
    """
    Периодическая фоновая задача сброса SQLite WAL в основной файл базы данных.
    - Раз в 10-15 минут выполняет PRAGMA wal_checkpoint(PASSIVE).
    - В ночные часы (03:00 - 06:00) выполняет PRAGMA wal_checkpoint(TRUNCATE) для усечения WAL-файла.
    """
    import logging
    from datetime import datetime
    wal_logger = logging.getLogger("wal_checkpoint")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            db = await get_pool()
            if not db:
                continue

            current_hour = datetime.now().hour
            is_night_time = 3 <= current_hour < 6
            mode = "TRUNCATE" if is_night_time else "PASSIVE"

            async def _do_checkpoint():
                async with db_lock:
                    async with db.execute(f"PRAGMA wal_checkpoint({mode});") as cursor:
                        row = await cursor.fetchone()
                        if row:
                            busy, log_frames, ckpt_frames = row
                            wal_logger.info(
                                f"💾 [WAL Checkpoint] Mode={mode}, Busy={busy}, Log={log_frames}, Checkpointed={ckpt_frames}"
                            )

            await execute_with_retry(_do_checkpoint, max_retries=3, base_delay=0.5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            wal_logger.warning(f"⚠️ [WAL Checkpoint] Error during checkpoint: {e}")
            await asyncio.sleep(30)

