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
    "metadata",
    "instance-data",
    "instance-data.ec2.internal",
    "169.254.169.254",
    "169.254.170.2",
    "127.0.0.1",
    "::1",
    "[::1]",
}

def _is_ip_safe(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
        or ip_obj.is_reserved
    ):
        return False
    if hasattr(ip_obj, "ipv4_mapped") and ip_obj.ipv4_mapped:
        mapped = ip_obj.ipv4_mapped
        if (
            mapped.is_loopback
            or mapped.is_private
            or mapped.is_link_local
            or mapped.is_multicast
            or mapped.is_unspecified
            or mapped.is_reserved
        ):
            return False
    return True

def is_safe_url(url: str, allowed_domains: set[str] | None = None) -> bool:
    """Validates that a URL is safe to fetch (protects against SSRF attacks).

    Checks:
    - Scheme must be http or https
    - Hostname must be present and not in known metadata/internal hostnames
    - Ports must be standard web ports (80, 443, 8080, 8443) or omitted
    - Resolved IP addresses must not be private, loopback, link-local (e.g. 169.254.169.254),
      multicast, unspecified, or reserved. Handles IPv4-mapped IPv6 addresses.
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
        if parsed.port is not None and parsed.port not in (80, 443, 8080, 8443):
            return False
        if allowed_domains:
            if not any(hostname == d or hostname.endswith("." + d) for d in allowed_domains):
                return False

        # Numeric / Hex representation check (e.g. http://2130706433/ or http://0x7f000001/)
        if hostname.isdigit():
            try:
                ip_int = int(hostname)
                if 0 <= ip_int <= 0xFFFFFFFF:
                    ip_obj = ipaddress.ip_address(ip_int)
                    if not _is_ip_safe(ip_obj):
                        return False
            except ValueError:
                return False
        elif hostname.startswith("0x"):
            try:
                ip_hex = int(hostname, 16)
                if 0 <= ip_hex <= 0xFFFFFFFF:
                    ip_obj = ipaddress.ip_address(ip_hex)
                    if not _is_ip_safe(ip_obj):
                        return False
            except ValueError:
                return False

        try:
            ip_obj = ipaddress.ip_address(hostname)
            if not _is_ip_safe(ip_obj):
                return False
        except ValueError:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for item in addr_info:
                    sockaddr = item[4]
                    ip_str = sockaddr[0]
                    ip_obj = ipaddress.ip_address(ip_str)
                    if not _is_ip_safe(ip_obj):
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
    """
    Периодическая полная очистка просроченных IP из истории запросов, банов и PoW кэша.
    Предотвращает утечки памяти при распределенных атаках.
    """
    now = time.time()
    # 1. Prune REQUEST_HISTORY
    expired_history = [ip for ip, data in list(REQUEST_HISTORY.items()) if not data or now - data[1] > RATE_LIMIT_WINDOW * 2]
    for ip in expired_history:
        REQUEST_HISTORY.pop(ip, None)

    # 2. Prune IP_BAN_LIST
    expired_bans = [ip for ip, expiry in list(IP_BAN_LIST.items()) if now >= expiry]
    for ip in expired_bans:
        IP_BAN_LIST.pop(ip, None)

    # 3. Prune POW_CACHE
    expired_pow = [ch for ch, exp in list(POW_CACHE.items()) if now >= exp]
    for ch in expired_pow:
        POW_CACHE.pop(ch, None)


def verify_pow(challenge: str, nonce: str, difficulty: int = DEFAULT_POW_DIFFICULTY) -> bool:
    """Проверяет решение с валидацией срока жизни и защиты от replay-атак."""
    if not isinstance(difficulty, int) or difficulty < 0:
        return False
    if difficulty == 0:
        return True

    # Проверяем типы и наличие челленджа в кэше
    if not challenge or not nonce or not isinstance(challenge, str) or not isinstance(nonce, str):
        return False

    now = time.time()
    expiry = POW_CACHE.get(challenge)
    if expiry is None:
        return False
    if expiry < now:
        POW_CACHE.pop(challenge, None)
        return False

    target = "0" * difficulty
    text = f"{challenge}{nonce}"
    # Считаем хеш
    res = hashlib.sha256(text.encode("utf-8")).hexdigest()

    if res.startswith(target):
        POW_CACHE.pop(challenge, None)
        return True
    return False

IP_BAN_LIST = {}
# REQUEST_HISTORY теперь хранит { ip: [count, window_start_ts] }
REQUEST_HISTORY = {}
MAX_HISTORY_SIZE = 10000 # Максимальное кол-во IP в памяти
MAX_BAN_LIST_SIZE = 10000

RATE_LIMIT_WINDOW = 5
MAX_REQUESTS_PER_WINDOW = 200
BAN_TIME = 60

def check_ddos(ip: str) -> bool:
    if not ip or not isinstance(ip, str):
        return False
    ip = ip.strip()
    if not ip:
        return False

    # Канонизируем IP-адрес для предотвращения обхода через разные форматы записи (IPv4/IPv6)
    try:
        ip = str(ipaddress.ip_address(ip))
    except ValueError:
        pass

    now = time.time()

    # 1. Вероятностная очистка старых записей (раз в ~100 вызовов) или при превышении лимита
    if random.random() < 0.01 or len(REQUEST_HISTORY) > MAX_HISTORY_SIZE or len(IP_BAN_LIST) > MAX_BAN_LIST_SIZE:
        # Удаляем все записи истории, где окно времени (5 сек) уже давно истекло
        expired_ips = [k for k, v in list(REQUEST_HISTORY.items()) if now - v[1] > RATE_LIMIT_WINDOW * 2]
        for k in expired_ips:
            REQUEST_HISTORY.pop(k, None)

        # Удаляем все истекшие баны из IP_BAN_LIST
        expired_bans = [k for k, exp in list(IP_BAN_LIST.items()) if now >= exp]
        for k in expired_bans:
            IP_BAN_LIST.pop(k, None)

        # Если всё еще перебор (агрессивный флуд новыми IP), чистим 20% самых старых
        if len(REQUEST_HISTORY) > MAX_HISTORY_SIZE:
            keys = list(REQUEST_HISTORY.keys())
            for k in keys[:len(keys)//5]:
                REQUEST_HISTORY.pop(k, None)

        if len(IP_BAN_LIST) > MAX_BAN_LIST_SIZE:
            b_keys = list(IP_BAN_LIST.keys())
            for k in b_keys[:len(b_keys)//5]:
                IP_BAN_LIST.pop(k, None)

    if ip in IP_BAN_LIST:
        if now < IP_BAN_LIST[ip]:
            return True
        IP_BAN_LIST.pop(ip, None)

    record = REQUEST_HISTORY.get(ip)

    if not record or (now - record[1] > RATE_LIMIT_WINDOW):
        REQUEST_HISTORY[ip] = [1, now]
        return False

    record[0] += 1

    if record[0] > MAX_REQUESTS_PER_WINDOW:
        logger.warning(f"🛡️ DDoS DETECTED: Ban IP {ip} for {BAN_TIME}s")
        IP_BAN_LIST[ip] = now + BAN_TIME
        REQUEST_HISTORY.pop(ip, None)
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
