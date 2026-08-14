import hashlib
import secrets
import time
import logging
import random
import os
import hmac
from urllib.parse import parse_qsl

logger = logging.getLogger("security")

# --- PoW (Защита от спама) ---
POW_CACHE = {}
MAX_POW_CACHE_SIZE = 5000 # Лимит для предотвращения утечки памяти
DEFAULT_POW_DIFFICULTY = 4 

def generate_challenge_str() -> str:
    """Генерирует строку и чистит кэш."""
    now = time.time()
    
    # 1. Агрессивная очистка при превышении лимита или по истечении времени
    if len(POW_CACHE) > MAX_POW_CACHE_SIZE or random.random() < 0.1:
        to_del = [k for k, v in POW_CACHE.items() if v < now]
        # Если кэш всё еще переполнен (атака), удаляем 20% случайных записей
        if len(POW_CACHE) > MAX_POW_CACHE_SIZE:
            keys = list(POW_CACHE.keys())
            to_del.extend(random.sample(keys, len(keys) // 5))
            
        for k in to_del:
            POW_CACHE.pop(k, None)
    
    challenge = secrets.token_hex(16)
    POW_CACHE[challenge] = now + 600 
    return challenge

def get_pow_challenge_data(difficulty: int = DEFAULT_POW_DIFFICULTY) -> dict:
    """
    Возвращает данные для отправки на фронтенд.
    Используется в API /api/pow/challenge.
    """
    challenge = generate_challenge_str()
    return {
        "challenge": challenge, 
        "difficulty": difficulty
    }
def cleanup_ddos_history():
    now = time.time()
    dead_ips = [ip for ip, history in REQUEST_HISTORY.items() if not history or history[-1] < now - 600]
    for ip in dead_ips:
        del REQUEST_HISTORY[ip]


def verify_pow(challenge: str, nonce: str, difficulty: int = DEFAULT_POW_DIFFICULTY) -> bool:
    """Проверяет решение."""
    if difficulty == 0: return True
    
    # Проверяем, выдавали ли мы такой челлендж
    if not challenge or not nonce or challenge not in POW_CACHE: 
        return False
    
    target = "0" * difficulty
    text = f"{challenge}{nonce}"
    # Считаем хеш
    res = hashlib.sha256(text.encode()).hexdigest()
    
    if res.startswith(target):
        del POW_CACHE[challenge]
        return True
    return False

IP_BAN_LIST = {}
# REQUEST_HISTORY теперь хранит { ip: [count, window_start_ts] }
REQUEST_HISTORY = {}
MAX_HISTORY_SIZE = 10000 # Максимальное кол-во IP в памяти

RATE_LIMIT_WINDOW = 5
MAX_REQUESTS_PER_WINDOW = 200
BAN_TIME = 60 

def check_ddos(ip: str) -> bool:
    now = time.time()

    # 1. Вероятностная очистка старых записей (раз в ~100 вызовов)
    if random.random() < 0.01 or len(REQUEST_HISTORY) > MAX_HISTORY_SIZE:
        # Удаляем все записи, где окно времени (5 сек) уже давно истекло
        expired_ips = [k for k, v in REQUEST_HISTORY.items() if now - v[1] > RATE_LIMIT_WINDOW * 2]
        for k in expired_ips:
            REQUEST_HISTORY.pop(k, None)
        
        # Если всё еще перебор (агрессивный флуд новыми IP), чистим 20% самых старых
        if len(REQUEST_HISTORY) > MAX_HISTORY_SIZE:
            keys = list(REQUEST_HISTORY.keys())
            for k in keys[:len(keys)//5]:
                REQUEST_HISTORY.pop(k, None)

    if ip in IP_BAN_LIST:
        if now < IP_BAN_LIST[ip]:
            return True
        del IP_BAN_LIST[ip]

    record = REQUEST_HISTORY.get(ip)
    
    if not record or (now - record[1] > RATE_LIMIT_WINDOW):
        REQUEST_HISTORY[ip] = [1, now]
        return False
    
    record[0] += 1
    
    if record[0] > MAX_REQUESTS_PER_WINDOW:
        logger.warning(f"🛡️ DDoS DETECTED: Ban IP {ip} for {BAN_TIME}s")
        IP_BAN_LIST[ip] = now + BAN_TIME
        if ip in REQUEST_HISTORY:
            del REQUEST_HISTORY[ip]
        return True

    return False

def verify_telegram_webapp_data(init_data: str) -> dict | None:
    """Verifies Telegram WebApp initData and returns parsed dict if valid.

    Tries every *_BOT_TOKEN variable found in the environment so that
    multiple bots pointing at the same site all work without extra config.
    """
    # Collect all non-empty *_BOT_TOKEN values (deduplicated, order stable).
    seen: set[str] = set()
    tokens: list[str] = []
    for key, val in os.environ.items():
        if key.endswith("_BOT_TOKEN") and val and val not in seen:
            seen.add(val)
            tokens.append(val)

    if not tokens:
        logger.error("No *_BOT_TOKEN variables found in env")
        return None

    try:
        parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed_data:
            return None

        received_hash = parsed_data.pop("hash")

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed_data.items())
        )

        for bot_token in tokens:
            secret_key = hmac.new(
                b"WebAppData",
                bot_token.encode("utf-8"),
                hashlib.sha256,
            ).digest()

            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if hmac.compare_digest(calculated_hash, received_hash):
                return parsed_data  # valid — return without "hash" key

        logger.warning("TMA initData hash mismatch against all %d known bot tokens", len(tokens))
        return None

    except Exception as e:
        logger.error("Error verifying TMA auth: %s", e)
        return None