"""
Безопасная временная подмена переменных окружения.

os.environ — состояние ПРОЦЕССА, а не потока. Загрузчики на HuggingFace
переключали стратегию «прямо / через прокси», выкидывая HTTPS_PROXY и
HTTP_PROXY из os.environ и НЕ возвращая их назад:

    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.update(strategy["env"])

При этом клиентские сессии создаются с trust_env=True (main.py:20948,
site_tgach/main.py:239 и :6601, Dubsite_tgach/main.py:133 и :4071) — они берут
прокси именно из окружения. То есть фоновая загрузка картинок молча снимала
прокси со ВСЕГО процесса, включая трафик к Telegram API, и итоговое состояние
зависело от того, какая стратегия отработала последней.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable, Mapping
from contextlib import contextmanager

# Замок именно threading: подмена происходит в потоках экзекьютора, а os.environ
# один на процесс. Пока переменные подменены, другой поток не должен их трогать —
# иначе стратегии двух загрузок перетирают друг друга.
_env_lock = threading.RLock()


@contextmanager
def temporary_env(overrides: Mapping[str, str] | None = None,
                  remove: Iterable[str] = ()):
    """
    Подменяет переменные окружения на время блока и ВСЕГДА возвращает как было.

    overrides: {имя: значение}; значение None означает «удалить».
    remove:    имена, которые нужно убрать на время блока.

    Восстановление идёт в finally, поэтому исключение внутри блока
    (а загрузки на HF падают регулярно) не оставляет процесс без прокси.

    Блок сериализован по _env_lock. Это осознанный компромисс: os.environ
    глобален, поэтому параллельные подмены в принципе некорректны, и
    последовательное выполнение — единственный способ получить предсказуемое
    поведение.
    """
    overrides = dict(overrides or {})
    keys = set(overrides) | set(remove)
    with _env_lock:
        saved = {key: os.environ.get(key) for key in keys}
        try:
            for key in remove:
                os.environ.pop(key, None)
            for key, value in overrides.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            yield
        finally:
            for key, previous in saved.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous


PROXY_ENV_KEYS = ("HTTPS_PROXY", "HTTP_PROXY")


@contextmanager
def proxy_env(proxy_url: str | None):
    """
    Готовый вариант для стратегий загрузки: proxy_url=None означает
    «идти напрямую», строка — «через этот прокси». Прежние значения
    восстанавливаются после блока.
    """
    if proxy_url:
        with temporary_env({key: proxy_url for key in PROXY_ENV_KEYS}):
            yield
    else:
        with temporary_env(remove=PROXY_ENV_KEYS):
            yield
