import aiosqlite
import asyncio
from common.config import DB_NAME

# Глобальная переменная соединения
_db_connection = None

# ГАРАНТИЯ БЕЗОПАСНОСТИ:
# Этот замок (Lock) не даст боту и сайту одновременно пытаться пересоздать подключение.
_reconnect_lock = asyncio.Lock()

# Глобальный замок для синхронизации задач внутри одного процесса (Task-Safety).
# Обязателен при использовании ручных транзакций (BEGIN IMMEDIATE), 
# чтобы задачи не вклинивались в чужие транзакции.
db_lock = asyncio.Lock()

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
            pass # Если проверка не удалась, идем на восстановление

    # 2. Если соединения нет или оно мертвое — входим в режим восстановления
    async with _reconnect_lock:
        # Повторная проверка внутри замка
        if _db_connection is not None:
            try:
                if _db_connection._running and _db_connection._conn:
                    return _db_connection
            except Exception:
                pass
            print("⚠️ [DB] Обнаружен разрыв соединения. Запуск безопасного восстановления...")
        
        # 3. Аккуратное закрытие старого трупа (если есть)
        if _db_connection:
            try:
                await _db_connection.close()
            except Exception: 
                pass
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
                await conn.execute("PRAGMA cache_size = -819200;")
                await conn.execute("PRAGMA foreign_keys = ON;")
                # Нет await conn.commit(), так как мы в режиме autocommit (isolation_level=None)
                
                _db_connection = conn
                print(f"✅ [DB] Восстановлено (попытка {attempt+1}, isolation_level=None)")
                return _db_connection
            except Exception as e:
                print(f"⚠️ [DB] Retry {attempt+1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)  # Backoff перед retry
                else:
                    print(f"⛔ [DB] КРИТИЧЕСКАЯ ОШИБКА: {e}")
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
                print("🔌 [DB] Соединение корректно закрыто.")
            except Exception as e:
                print(f"⚠️ [DB] Ошибка при закрытии: {e}")
            finally:
                _db_connection = None