import aiosqlite
import asyncio
import atexit
import sqlite3
import os
import logging
import contextvars
import time
from common.config import DB_NAME

logger = logging.getLogger("db_pool")

# Отслеживание глубины транзакций для конкретной asyncio задачи (с защитой от утечек в дочерние таски)
class _TaskTxDepthWrapper:
    """
    Изолирует глубину транзакций по конкретным asyncio задачам.
    Предотвращает утечку глубины транзакций в дочерние таски при asyncio.create_task(),
    гарантируя, что дочерние таски всегда стартуют с depth = 0.
    """
    def __init__(self):
        self._var = contextvars.ContextVar("_task_tx_depth_tuple", default=(None, 0))

    def get(self, default: int = 0) -> int:
        try:
            cur = asyncio.current_task()
        except RuntimeError:
            cur = None
        task, depth = self._var.get()
        if task is not cur:
            return default
        return depth

    def set(self, depth: int):
        try:
            cur = asyncio.current_task()
        except RuntimeError:
            cur = None
        self._var.set((cur, depth))

_task_tx_depth = _TaskTxDepthWrapper()


def _patch_aiosqlite_safe_worker():
    """
    Защищает рабочий поток aiosqlite от краша с RuntimeError('Event loop is closed')
    при завершении работы бота и закрытии asyncio event loop.
    """
    try:
        import aiosqlite.core
        if getattr(aiosqlite.core.Connection, "_safe_worker_patched", False):
            return

        def _safe_run(self):
            while True:
                tx_item = self._tx.get()
                if tx_item is aiosqlite.core._STOP_RUNNING_SENTINEL:
                    break

                future, function = tx_item

                try:
                    result = function()
                    loop = getattr(future, "get_loop", None)
                    if loop:
                        ev_loop = loop()
                        if ev_loop and not ev_loop.is_closed():
                            try:
                                ev_loop.call_soon_threadsafe(aiosqlite.core.set_result, future, result)
                            except RuntimeError:
                                pass
                except BaseException as e:
                    try:
                        loop = getattr(future, "get_loop", None)
                        if loop:
                            ev_loop = loop()
                            if ev_loop and not ev_loop.is_closed():
                                try:
                                    ev_loop.call_soon_threadsafe(aiosqlite.core.set_exception, future, e)
                                except RuntimeError:
                                    pass
                    except Exception:
                        pass

        aiosqlite.core.Connection.run = _safe_run
        aiosqlite.core.Connection._safe_worker_patched = True
    except Exception as e:
        print(f"[DB] Could not patch aiosqlite worker: {e}")


_patch_aiosqlite_safe_worker()

# Глобальная переменная соединения
_db_connection = None


def _sync_wal_checkpoint_truncate():
    """
    Синхронный сброс WAL при завершении процесса Python (через atexit).
    Гарантирует, что даже при выходе из процесса без вызова close_pool(),
    WAL сбрасывается и сжимается до 0 байт.
    """
    db_path = str(DB_NAME) if DB_NAME else None
    if not db_path or not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path, timeout=3.0)
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
        self._acquired_at = 0.0
        self._high_waiters = []  # list of (asyncio.Future, asyncio.Task)
        self._low_waiters = []   # list of (asyncio.Future, asyncio.Task)

    def _ensure_loop(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._lock is None or (loop and self._loop is not loop):
            self._lock = asyncio.Lock()
            self._loop = loop
            self._owner = None
            self._depth = 0
            self._acquired_at = 0.0
            self._high_waiters.clear()
            self._low_waiters.clear()
        return loop

    def _get_lock(self):
        self._ensure_loop()
        return self._lock

    def locked(self) -> bool:
        self._ensure_loop()
        return self._owner is not None

    def is_owned_by_current_task(self) -> bool:
        """Проверяет, удерживает ли текущая задача этот замок."""
        self._ensure_loop()
        if self._owner is None:
            return False
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if self._owner is not None and getattr(self._owner, "done", lambda: False)():
            return False
        return current is not None and self._owner is current

    def locked_by_current_task(self) -> bool:
        """Алиас/хелпер для проверки владения замком текущей задачей."""
        return self.is_owned_by_current_task()

    def has_pending_high_priority(self) -> bool:
        """Проверяет, ожидают ли высокоприоритетные задачи (например, входящие посты)."""
        self._ensure_loop()
        return any(not fut.done() for fut, _ in self._high_waiters)

    def _check_watchdog(self):
        if self._owner is None:
            return
        now = time.monotonic()
        is_hung = self._acquired_at > 0.0 and (now - self._acquired_at > 20.0)
        is_dead = getattr(self._owner, "done", lambda: False)()
        if is_dead or is_hung:
            duration = f"{now - self._acquired_at:.1f}s" if self._acquired_at > 0 else "unknown"
            owner_desc = f"{self._owner}" if self._owner else "None"
            stack_info = ""
            if self._owner and hasattr(self._owner, "get_stack"):
                try:
                    import traceback
                    frames = self._owner.get_stack()
                    if frames:
                        stack_info = "\n" + "".join(traceback.format_stack(frames[-1]))
                except Exception:
                    pass
            reason = "завершился (done)" if is_dead else f"удерживает замок > 20с ({duration})"
            logger.critical(
                f"🚨 [LAZY_LOCK] Принудительный сброс замка! Владелец {reason}: {owner_desc}{stack_info}"
            )
            self._depth = 0
            self._owner = None
            self._acquired_at = 0.0
            if self._lock and self._lock.locked():
                try:
                    self._lock.release()
                except RuntimeError:
                    pass
            self._wake_next()

    def _wake_next(self):
        while self._high_waiters:
            fut, task = self._high_waiters.pop(0)
            if not fut.done():
                self._owner = task
                self._depth = 1
                self._acquired_at = time.monotonic()
                fut.set_result(True)
                return
        while self._low_waiters:
            fut, task = self._low_waiters.pop(0)
            if not fut.done():
                self._owner = task
                self._depth = 1
                self._acquired_at = time.monotonic()
                fut.set_result(True)
                return

    async def acquire(self, timeout: float = None, priority: bool = False) -> bool:
        loop = self._ensure_loop()
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None

        # Реентерабельный повторный захват из той же таски
        if current is not None and self._owner is current:
            self._depth += 1
            return True

        self._check_watchdog()

        if self._owner is None:
            if priority or not self.has_pending_high_priority():
                self._owner = current
                self._depth = 1
                self._acquired_at = time.monotonic()
                return True

        fut = loop.create_future()
        waiter_entry = (fut, current)
        if priority:
            self._high_waiters.append(waiter_entry)
        else:
            self._low_waiters.append(waiter_entry)

        start_time = time.monotonic()
        try:
            while not fut.done():
                self._check_watchdog()
                if fut.done():
                    break
                elapsed = time.monotonic() - start_time
                if timeout is not None and elapsed >= timeout:
                    raise asyncio.TimeoutError()
                wait_chunk = 5.0
                if timeout is not None:
                    wait_chunk = min(wait_chunk, timeout - elapsed)
                try:
                    await asyncio.wait_for(asyncio.shield(fut), timeout=wait_chunk)
                except asyncio.TimeoutError:
                    pass
            return True
        except BaseException:
            if waiter_entry in self._high_waiters:
                self._high_waiters.remove(waiter_entry)
            if waiter_entry in self._low_waiters:
                self._low_waiters.remove(waiter_entry)
            if fut.done() and not fut.cancelled() and fut.exception() is None:
                self._owner = current
                self._depth = 1
                self._acquired_at = time.monotonic()
                self.release()
            raise

    def release(self):
        self._ensure_loop()
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None

        if current is not None and self._owner is current:
            self._depth -= 1
            if self._depth <= 0:
                self._depth = 0
                self._owner = None
                self._acquired_at = 0.0
                if self._lock and self._lock.locked():
                    try:
                        self._lock.release()
                    except RuntimeError:
                        pass
                self._wake_next()
        elif self._owner is None or getattr(self._owner, "done", lambda: False)():
            self._depth = 0
            self._owner = None
            self._acquired_at = 0.0
            if self._lock and self._lock.locked():
                try:
                    self._lock.release()
                except RuntimeError:
                    pass
            self._wake_next()

    def prioritized(self):
        """Контекстный менеджер для приоритетного захвата замка."""
        return _PrioritizedLockContext(self)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.is_owned_by_current_task():
            self.release()


class _PrioritizedLockContext:
    def __init__(self, lock: LazyLock):
        self._lock = lock

    async def __aenter__(self):
        await self._lock.acquire(priority=True)
        return self._lock

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()


def has_pending_high_priority() -> bool:
    """Глобальный хелпер: проверяет наличие ожидающих высокоприоритетных запросов к БД."""
    fn = getattr(db_lock, "has_pending_high_priority", None)
    return fn() if callable(fn) else False

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
                conn = await aiosqlite.connect(DB_NAME, timeout=30.0, isolation_level=None)

                await conn.execute("PRAGMA busy_timeout = 25000;")
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous = NORMAL;")
                await conn.execute("PRAGMA temp_store = MEMORY;")
                await conn.execute("PRAGMA mmap_size = 134217728;")
                await conn.execute("PRAGMA cache_size = -32768;")

                await conn.execute("PRAGMA foreign_keys = ON;")
                await conn.execute("PRAGMA wal_autocheckpoint=500;")
                # Нет await conn.commit(), так как мы в режиме autocommit (isolation_level=None)

                _db_connection = conn
                print(f"[DB] Connected successfully (attempt {attempt+1}, isolation_level=None)")
                return _db_connection
            except Exception as e:
                if "Production DB / Bot access forbidden" in str(e):
                    raise e
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

async def wal_checkpoint_truncate(db=None, timeout: float = 5.0) -> bool:
    """
    Принудительный асинхронный сброс всех данных из WAL в основной файл базы данных
    и усечение WAL-файла до 0 байт (PRAGMA wal_checkpoint(TRUNCATE)).
    Защищен таймаутом timeout (по умолчанию 5.0с) для предотвращения дедлоков event loop.
    """
    global _db_connection
    try:
        async def _do_truncate():
            async with db_lock:
                conn = db or _db_connection
                if conn is None:
                    return True
                async with conn.execute("PRAGMA wal_checkpoint(TRUNCATE);") as cursor:
                    row = await cursor.fetchone()
                    if row:
                        busy, log_frames, ckpt_frames = row
                        print(f"[DB] WAL Checkpoint (TRUNCATE): Busy={busy}, Log={log_frames}, Checkpointed={ckpt_frames}")
                        return busy == 0
                    return True

        return await asyncio.wait_for(_do_truncate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning(f"[DB] WAL Checkpoint (TRUNCATE) timed out after {timeout:.1f}s")
    except Exception as e:
        print(f"[DB] WAL Checkpoint (TRUNCATE) error: {e}")
    return False


async def close_pool():
    """Безопасное закрытие при выключении бота с обязательным TRUNCATE чекпоинтом."""
    global _db_connection
    async with _reconnect_lock:
        if _db_connection:
            conn = _db_connection
            try:
                try:
                    await asyncio.wait_for(conn.execute("PRAGMA wal_checkpoint(TRUNCATE);"), timeout=5.0)
                    print("[DB] WAL checkpoint (TRUNCATE) completed successfully before close.")
                except (asyncio.TimeoutError, TimeoutError):
                    print("[DB] WAL checkpoint on close timed out after 5.0s, proceeding to close.")
                except Exception as ckpt_e:
                    print(f"[DB] WAL checkpoint on close error: {ckpt_e}")
                await conn.close()
                is_alive_fn = getattr(conn, "is_alive", None)
                if callable(is_alive_fn) and not asyncio.iscoroutinefunction(is_alive_fn):
                    try:
                        alive = is_alive_fn()
                        if alive and not asyncio.iscoroutine(alive):
                            await asyncio.wait_for(asyncio.to_thread(conn.join, 2.0), timeout=2.5)
                    except Exception:
                        pass
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
            db_lock._acquired_at = 0.0
            if hasattr(db_lock, "_wake_next"):
                db_lock._wake_next()
            elif db_lock._lock and db_lock._lock.locked():
                try:
                    db_lock._lock.release()
                except RuntimeError:
                    pass
        except RuntimeError:
            saved_depth = 0
    try:
        await asyncio.sleep(delay)
    finally:
        if saved_depth > 0:
            await db_lock.acquire(priority=True)
            db_lock._depth = saved_depth


async def reset_orphaned_transaction(db=None) -> bool:
    """
    Проверяет наличие зависшей/осиротевшей транзакции на соединении и принудительно
    сбрасывает её через ROLLBACK.
    Учитывает, что при isolation_level=None свойство conn.in_transaction может быть False
    даже при незавершенной активной транзакции в SQLite.
    Возвращает True, если был выполнен ROLLBACK.
    """
    global _db_connection
    conn = db or _db_connection
    if not conn:
        return False
    try:
        await conn.execute("ROLLBACK")
        logger.warning("🔄 [DB_POOL] Успешно сброшена зависшая транзакция на соединении через ROLLBACK.")
        return True
    except Exception as e:
        err_msg = str(e).lower()
        if "no transaction is active" not in err_msg and "cannot rollback" not in err_msg:
            logger.error(f"❌ [DB_POOL] Ошибка сброса зависшей транзакции: {e}")
    return False


class db_transaction:
    """
    Асинхронный контекстный менеджер для безопасного выполнения транзакций.
    - Автоматически захватывает db_lock (если текущая задача им еще не владеет).
    - Поддерживает приоритезацию (priority=True) для критических операций (create_post).
    - Защищает от дедлоков и утечек при отмене задач / таймаутах (shielded ROLLBACK).
    - Автоматически обнаруживает и откатывает (ROLLBACK) зависшие осиротевшие транзакции.
    - Предотвращает ошибки SQLite 'cannot start a transaction within a transaction'
      путем использования SAVEPOINT при вложенных транзакциях.
    - Поддерживает автоматический retry при sqlite3.OperationalError: database is locked / busy.
    - Гарантирует отсутствие 'cannot commit - no transaction is active' и 'cannot rollback'.
    - Корректно откатывает только свой savepoint при вложенной ошибке или всю транзакцию на верхнем уровне.
    """
    _sp_counter = 0

    def __init__(self, db=None, immediate: bool = True, max_retries: int = 5, base_delay: float = 0.1, priority: bool = False):
        self.db = db
        self.immediate = immediate
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.priority = priority
        self._is_nested = False
        self._savepoint_name = None
        self._lock_acquired = False
        self._tx_started = False

    async def __aenter__(self):
        is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
        is_owned = is_owned_fn() if callable(is_owned_fn) else False
        if not is_owned:
            try:
                await db_lock.acquire(priority=self.priority)
                self._lock_acquired = True
            except BaseException:
                if self._lock_acquired:
                    db_lock.release()
                    self._lock_acquired = False
                raise

        try:
            if self.db is None:
                self.db = await get_pool()

            depth = _task_tx_depth.get()
            if depth == 0:
                self._is_nested = False
                # Проверяем наличие осиротевшей транзакции от предыдущего отмененного таска
                await reset_orphaned_transaction(self.db)
            else:
                self._is_nested = True

            for attempt in range(self.max_retries):
                try:
                    if self._is_nested:
                        db_transaction._sp_counter += 1
                        self._savepoint_name = f"sp_{id(self)}_{db_transaction._sp_counter}"
                        await self.db.execute(f"SAVEPOINT {self._savepoint_name}")
                    else:
                        if self.immediate:
                            await self.db.execute("BEGIN IMMEDIATE")
                        else:
                            await self.db.execute("BEGIN")
                    self._tx_started = True
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if "cannot start a transaction within a transaction" in err_str:
                        logger.warning(
                            "⚠️ [DB_POOL] Обнаружена незакрытая транзакция при BEGIN IMMEDIATE (isolation_level=None). "
                            "Выполняем ROLLBACK и повторяем попытку..."
                        )
                        try:
                            await self.db.execute("ROLLBACK")
                        except Exception as rb_err:
                            logger.error(f"❌ [DB_POOL] Ошибка ROLLBACK при сбросе транзакции: {rb_err}")

                        if self._is_nested:
                            await self.db.execute(f"SAVEPOINT {self._savepoint_name}")
                        else:
                            if self.immediate:
                                await self.db.execute("BEGIN IMMEDIATE")
                            else:
                                await self.db.execute("BEGIN")
                        self._tx_started = True
                        break

                    if ("locked" in err_str or "busy" in err_str) and attempt < self.max_retries - 1:
                        if self._lock_acquired:
                            db_lock.release()
                            self._lock_acquired = False
                        await asyncio.sleep(self.base_delay * (2 ** attempt))
                        if not is_owned:
                            await db_lock.acquire(priority=self.priority)
                            self._lock_acquired = True
                    else:
                        raise

            _task_tx_depth.set(depth + 1)
            return self.db
        except BaseException:
            # Если в __aenter__ случилась отмена задачи или ошибка ПОСЛЕ или ВО ВРЕМЯ попытки BEGIN / SAVEPOINT,
            # мы обязаны гарантировать откат через shielded ROLLBACK, чтобы соединение не осталось с зомби-транзакцией!
            if getattr(self, "db", None) is not None:
                async def _abort_enter():
                    try:
                        if self._is_nested and self._savepoint_name:
                            try:
                                await self.db.execute(f"ROLLBACK TO {self._savepoint_name}")
                                await self.db.execute(f"RELEASE {self._savepoint_name}")
                            except Exception:
                                pass
                        elif not self._is_nested:
                            try:
                                await self.db.execute("ROLLBACK")
                            except Exception:
                                pass
                    except BaseException:
                        pass
                try:
                    await asyncio.shield(_abort_enter())
                except BaseException:
                    pass
                self._tx_started = False

            # Гарантируем немедленное освобождение лока при любой ошибке или таймауте внутри __aenter__
            if self._lock_acquired:
                is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
                if callable(is_owned_fn) and is_owned_fn():
                    db_lock.release()
                self._lock_acquired = False
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            # ПРОВЕРКА ВЛАДЕНИЯ ЗАМКОМ:
            # Если сторожевой таймер (watchdog) сбросил замок из-за зависания (>20с),
            # мы больше не владеем соединением! Запрещено делать COMMIT или ROLLBACK,
            # иначе мы перезапишем или сломаем транзакцию нового владельца!
            is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
            is_owned = is_owned_fn() if callable(is_owned_fn) else False
            if not is_owned:
                logger.critical(
                    f"🚨 [DB_TRANSACTION] Сторожевой таймер сбросил замок у таски {asyncio.current_task()}! "
                    "Пропускаем COMMIT/ROLLBACK для предотвращения порчи данных нового владельца."
                )
                self._lock_acquired = False
                depth = _task_tx_depth.get()
                _task_tx_depth.set(max(0, depth - 1))
                if exc_type is None:
                    raise RuntimeError("Transaction lock was revoked by watchdog; transaction lost")
                return

            depth = _task_tx_depth.get()
            _task_tx_depth.set(max(0, depth - 1))

            if not self._tx_started:
                return

            if exc_type is not None:
                # Ошибка или отмена/таймаут - ОБЯЗАТЕЛЬНО выполняем ROLLBACK под shield!
                async def _do_rollback():
                    try:
                        if self._is_nested and self._savepoint_name:
                            try:
                                await self.db.execute(f"ROLLBACK TO {self._savepoint_name}")
                                await self.db.execute(f"RELEASE {self._savepoint_name}")
                            except Exception:
                                pass
                        else:
                            try:
                                await self.db.execute("ROLLBACK")
                            except Exception:
                                pass
                    except BaseException:
                        pass

                try:
                    await asyncio.shield(_do_rollback())
                except BaseException:
                    pass
            else:
                # Штатный выход - ОБЯЗАТЕЛЬНО под shield, чтобы внешняя отмена задачи во время COMMIT
                # не оставила зомби-транзакцию на соединении!
                async def _do_commit():
                    if self._is_nested and self._savepoint_name:
                        try:
                            await self.db.execute(f"RELEASE {self._savepoint_name}")
                        except Exception:
                            pass
                    else:
                        for commit_attempt in range(3):
                            try:
                                await self.db.execute("COMMIT")
                                return
                            except Exception as commit_err:
                                err_msg = str(commit_err).lower()
                                if "statements in progress" in err_msg and commit_attempt < 2:
                                    logger.warning(f"⚠️ [DB_POOL] Statements in progress during COMMIT, retrying ({commit_attempt + 1}/3)...")
                                    await asyncio.sleep(0.05)
                                    continue
                                elif "cannot commit - no transaction is active" in err_msg or "no transaction is active" in err_msg or "cannot commit" in err_msg:
                                    logger.warning(f"⚠️ [DB_POOL] COMMIT skipped, no active transaction: {commit_err}")
                                    return
                                else:
                                    logger.error(f"❌ [DB_POOL] COMMIT failed: {commit_err}")
                                    try:
                                        await self.db.execute("ROLLBACK")
                                    except Exception:
                                        pass
                                    raise

                try:
                    await asyncio.shield(_do_commit())
                except BaseException as commit_exc:
                    # Если COMMIT упал с ошибкой или был прерван, выполняем ROLLBACK под shield!
                    try:
                        await asyncio.shield(self.db.execute("ROLLBACK"))
                    except Exception:
                        pass
                    raise
        finally:
            if self._lock_acquired:
                is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
                if callable(is_owned_fn) and is_owned_fn():
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


async def safe_begin_immediate(db, priority: bool = False) -> bool:
    """
    Безопасно начинает транзакцию BEGIN IMMEDIATE, если транзакция еще не активна.
    Возвращает True, если транзакция была начата этим вызовом, иначе False.
    Гарантирует владение db_lock текущей задачей и отслеживает глубину через _task_tx_depth.
    """
    if db is None:
        db = await get_pool()

    is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
    if not (callable(is_owned_fn) and is_owned_fn()):
        await db_lock.acquire(priority=priority)

    depth = _task_tx_depth.get()
    if depth > 0:
        return False

    in_tx = getattr(db, "in_transaction", False)
    if not in_tx:
        conn = getattr(db, "_conn", None)
        if conn:
            in_tx = getattr(conn, "in_transaction", False)
    if in_tx:
        logger.warning("⚠️ [DB_POOL] safe_begin_immediate: обнаружена осиротевшая транзакция, сбрасываем...")
        await reset_orphaned_transaction(db)

    try:
        await db.execute("BEGIN IMMEDIATE")
        _task_tx_depth.set(depth + 1)
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "cannot start a transaction within a transaction" in err_str:
            logger.warning("⚠️ [DB_POOL] safe_begin_immediate: незакрытая транзакция, выполняем ROLLBACK и повторяем BEGIN IMMEDIATE...")
            try:
                await db.execute("ROLLBACK")
            except Exception:
                pass
            await db.execute("BEGIN IMMEDIATE")
            _task_tx_depth.set(depth + 1)
            return True
        raise


async def safe_commit(db, started_by_caller: bool = True):
    """
    Безопасно фиксирует транзакцию, если она активна и была начата данным контекстом.
    Корректно обновляет _task_tx_depth.
    """
    if not started_by_caller or db is None:
        return
    depth = _task_tx_depth.get()
    if depth > 1:
        _task_tx_depth.set(depth - 1)
        return

    is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
    is_owned = is_owned_fn() if callable(is_owned_fn) else False
    if not is_owned:
        logger.warning("[DB_POOL] safe_commit: lock is no longer owned by current task, skipping COMMIT.")
        _task_tx_depth.set(0)
        return

    try:
        await db.execute("COMMIT")
    except Exception as e:
        err_msg = str(e).lower()
        if "no transaction is active" in err_msg or "cannot commit" in err_msg:
            logger.warning(f"[DB_POOL] safe_commit: skipped, no active transaction: {e}")
        else:
            raise
    finally:
        _task_tx_depth.set(max(0, depth - 1))
        if depth <= 1:
            if callable(is_owned_fn) and is_owned_fn():
                db_lock.release()


async def safe_rollback(db, started_by_caller: bool = True):
    """
    Безопасно откатывает транзакцию, если она активна и была начата данным контекстом.
    Корректно обновляет _task_tx_depth.
    """
    if not started_by_caller or db is None:
        return
    depth = _task_tx_depth.get()
    if depth > 1:
        _task_tx_depth.set(depth - 1)
        return

    is_owned_fn = getattr(db_lock, "is_owned_by_current_task", None)
    is_owned = is_owned_fn() if callable(is_owned_fn) else False
    if not is_owned:
        logger.warning("[DB_POOL] safe_rollback: lock is no longer owned by current task, skipping ROLLBACK.")
        _task_tx_depth.set(0)
        return

    try:
        await db.execute("ROLLBACK")
    except Exception:
        pass
    finally:
        _task_tx_depth.set(max(0, depth - 1))
        if depth <= 1:
            if callable(is_owned_fn) and is_owned_fn():
                db_lock.release()


async def sqlite_wal_checkpoint_task(interval_seconds: int = 600, checkpoint_timeout: float = 5.0):
    """
    Периодическая фоновая задача сброса SQLite WAL в основной файл базы данных.
    - Раз в 10-15 минут выполняет PRAGMA wal_checkpoint(PASSIVE).
    - В ночные часы (03:00 - 06:00) выполняет PRAGMA wal_checkpoint(TRUNCATE) для усечения WAL-файла.
    - Защищена жестким asyncio.wait_for (по умолчанию 5.0с), чтобы никогда не блокировать event loop.
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

            try:
                await asyncio.wait_for(_do_checkpoint(), timeout=checkpoint_timeout)
            except (asyncio.TimeoutError, TimeoutError):
                wal_logger.warning(f"⚠️ [WAL Checkpoint] Mode={mode} timed out after {checkpoint_timeout}s, skipping.")
                # Если ночной TRUNCATE заблокировался, пробуем быстрый PASSIVE без ожидания
                if mode == "TRUNCATE":
                    try:
                        async def _fallback_passive():
                            async with db_lock:
                                await db.execute("PRAGMA wal_checkpoint(PASSIVE);")
                        await asyncio.wait_for(_fallback_passive(), timeout=2.0)
                        wal_logger.info("💾 [WAL Checkpoint] Fallback PASSIVE completed successfully.")
                    except Exception:
                        pass

        except asyncio.CancelledError:
            break
        except Exception as e:
            wal_logger.warning(f"⚠️ [WAL Checkpoint] Error during checkpoint: {e}")
            await asyncio.sleep(30)

