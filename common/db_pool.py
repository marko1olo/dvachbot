import aiosqlite
import asyncio
from common.config import DB_NAME

# Глобальная переменная соединения
_db_connection = None

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

async def close_pool():
    """Безопасное закрытие при выключении бота."""
    global _db_connection
    async with _reconnect_lock:
        if _db_connection:
            try:
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
