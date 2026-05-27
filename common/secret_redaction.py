from __future__ import annotations

import logging
import re
import hashlib
from typing import Any


TELEGRAM_TOKEN_PATTERN = re.compile(r"(?<!\d)\d{8,12}:[A-Za-z0-9_-]{30,}")
BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE)
HUGGINGFACE_TOKEN_PATTERN = re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")
GITHUB_TOKEN_PATTERN = re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")
OPENAI_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")
GROQ_TOKEN_PATTERN = re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")
TELEGRAM_TOKEN_REPLACEMENT = "<telegram-token-redacted>"
BEARER_TOKEN_REPLACEMENT = "Bearer <redacted>"
API_TOKEN_REPLACEMENT = "<api-token-redacted>"


def redact_secrets(value: Any) -> str:
    text = str(value)
    text = TELEGRAM_TOKEN_PATTERN.sub(TELEGRAM_TOKEN_REPLACEMENT, text)
    text = BEARER_TOKEN_PATTERN.sub(BEARER_TOKEN_REPLACEMENT, text)
    text = HUGGINGFACE_TOKEN_PATTERN.sub(API_TOKEN_REPLACEMENT, text)
    text = GITHUB_TOKEN_PATTERN.sub(API_TOKEN_REPLACEMENT, text)
    text = OPENAI_TOKEN_PATTERN.sub(API_TOKEN_REPLACEMENT, text)
    return GROQ_TOKEN_PATTERN.sub(API_TOKEN_REPLACEMENT, text)


def redact_log_arg(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    return value


def secret_fingerprint(value: Any) -> str:
    digest = hashlib.blake2s(str(value).encode("utf-8"), digest_size=4).hexdigest()
    return f"secret-{digest}"


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_log_arg(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_log_arg(value) for value in record.args)
        elif record.args:
            record.args = redact_log_arg(record.args)
        return True


_FILTER = SecretRedactionFilter()


def add_secret_redaction_filter(handler: logging.Handler) -> None:
    handler.addFilter(_FILTER)


def install_logging_redaction() -> None:
    root = logging.getLogger()
    root.addFilter(_FILTER)
    for handler in root.handlers:
        add_secret_redaction_filter(handler)
