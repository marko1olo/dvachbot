import hashlib
import secrets
import time
import logging
import random
import os
import hmac
import ipaddress
import socket
from urllib.parse import parse_qsl, urlparse

logger = logging.getLogger("security")

ALLOWED_IMPORT_DOMAINS = {
    "2ch.hk",
    "2ch.life",
    "4chan.org",
    "4channel.org",
    "4cdn.org",
    "dobrochan.net",
    "dobrochan.ru",
    "2chan.net",
    "arhivach.ng",
    "arhivach.top",
}

DISALLOWED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}

def is_safe_url(url: str, allowed_domains: set[str] | None = None) -> bool:
    """Validates that a URL is safe to fetch (protects against SSRF attacks).

    Checks:
    - Scheme must be http or https
    - Hostname must be present and not in known metadata/internal hostnames
    - Resolved IP addresses must not be private, loopback, link-local (e.g. 169.254.169.254),
      multicast, unspecified, or reserved.
    - If allowed_domains is provided, hostname must match or be a subdomain of one of them.
    """
    if not url or not isinstance(url, str):
        return False
    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if hostname in DISALLOWED_HOSTNAMES:
            return False
        if allowed_domains:
            if not any(hostname == d or hostname.endswith("." + d) for d in allowed_domains):
                return False
        try:
            ip_obj = ipaddress.ip_address(hostname)
            if (
                ip_obj.is_loopback
                or ip_obj.is_private
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_unspecified
                or ip_obj.is_reserved
            ):
                return False
        except ValueError:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for item in addr_info:
                    sockaddr = item[4]
                    ip_str = sockaddr[0]
                    ip_obj = ipaddress.ip_address(ip_str)
                    if (
                        ip_obj.is_loopback
                        or ip_obj.is_private
                        or ip_obj.is_link_local
                        or ip_obj.is_multicast
                        or ip_obj.is_unspecified
                        or ip_obj.is_reserved
                    ):
                        return False
            except (socket.gaierror, socket.herror, ValueError):
                return False
        return True
    except Exception:
        return False

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
        if (key == "BOT_TOKEN" or key.endswith("_BOT_TOKEN")) and val and val not in seen:
            seen.add(val)
            tokens.append(val)

    if not tokens:
        logger.error("No BOT_TOKEN or *_BOT_TOKEN variables found in env")
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
                # Validate freshness to prevent replay attacks (mandatory auth_date, max 24h = 86400s)
                auth_date_str = parsed_data.get("auth_date")
                if not auth_date_str:
                    logger.warning("TMA initData missing auth_date parameter")
                    return None

                try:
                    auth_date = int(auth_date_str)
                    now = int(time.time())
                    # Disallow timestamps older than 86400 seconds or drifting more than 60s into future
                    if (now - auth_date > 86400) or (auth_date > now + 60):
                        logger.warning("TMA initData expired or invalid time: auth_date=%d, now=%d", auth_date, now)
                        return None
                except (ValueError, TypeError):
                    logger.warning("TMA initData invalid auth_date format: %s", auth_date_str)
                    return None
                return parsed_data  # valid — return without "hash" key

        logger.warning("TMA initData hash mismatch against all %d known bot tokens", len(tokens))
        return None

    except Exception as e:
        logger.error("Error verifying TMA auth: %s", e)
        return None
