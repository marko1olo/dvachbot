"""
common/idempotency.py — Distributed & in-memory idempotency tracking and de-duplication.

Prevents double-submission and concurrent race conditions across:
- Scheduled broadcast posts (daily airdrop, insurance, Abu fund, newspaper, digests)
- User feedback and complaints (bot /feedback, /suggest, and web /api/feedback)
- Generic system tasks with a sliding time window.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("common.idempotency")


class IdempotencyTracker:
    """
    In-memory asyncio-safe idempotency tracking with sliding time-to-live (TTL).
    """

    def __init__(self, default_ttl: float = 30.0):
        self.default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._records: Dict[str, Dict[str, Any]] = {}

    def _cleanup_expired_unlocked(self, now: float) -> None:
        """Removes expired records to prevent unbounded memory growth."""
        expired_keys = [
            k for k, v in self._records.items()
            if v.get("expires_at", 0.0) <= now
        ]
        for k in expired_keys:
            self._records.pop(k, None)

    async def acquire(self, key: str, ttl: Optional[float] = None) -> bool:
        """
        Attempts to acquire an idempotency lock for `key`.
        Returns True if acquired (first time caller), False if already active/duplicate.
        """
        now = time.time()
        expiry_ttl = ttl if ttl is not None else self.default_ttl

        async with self._lock:
            # Auto-cleanup if size exceeds threshold
            if len(self._records) > 500:
                self._cleanup_expired_unlocked(now)

            record = self._records.get(key)
            if record and record.get("expires_at", 0.0) > now:
                # Key already active and not expired
                return False

            self._records[key] = {
                "status": "pending",
                "created_at": now,
                "expires_at": now + expiry_ttl,
                "result": None,
            }
            return True

    async def release(self, key: str) -> None:
        """Releases the key early (e.g. if the protected operation failed and can be retried)."""
        async with self._lock:
            self._records.pop(key, None)

    async def register_result(self, key: str, result: Any, ttl: Optional[float] = None) -> None:
        """
        Registers the completed result for `key` and extends/sets its TTL.
        Subsequent calls can retrieve this result via `get_result(key)`.
        """
        now = time.time()
        expiry_ttl = ttl if ttl is not None else self.default_ttl

        async with self._lock:
            self._records[key] = {
                "status": "completed",
                "created_at": now,
                "expires_at": now + expiry_ttl,
                "result": result,
            }

    async def get_result(self, key: str) -> Optional[Any]:
        """Returns the cached result if the key is completed and not expired; otherwise None."""
        now = time.time()
        async with self._lock:
            record = self._records.get(key)
            if not record:
                return None
            if record.get("expires_at", 0.0) <= now:
                self._records.pop(key, None)
                return None
            if record.get("status") == "completed":
                return record.get("result")
            return None

    async def is_duplicate(self, key: str) -> bool:
        """Checks whether the key is currently active or recently completed."""
        now = time.time()
        async with self._lock:
            record = self._records.get(key)
            if not record:
                return False
            if record.get("expires_at", 0.0) <= now:
                self._records.pop(key, None)
                return False
            return True

    @staticmethod
    def compute_content_hash(content: Any) -> str:
        """
        Computes a deterministic SHA-256 hash for content.
        If content is a dict, ignores transient keys like timestamps and hashes normalized payload.
        """
        if isinstance(content, dict):
            # Normalize payload: copy dict without ephemeral/transient keys
            normalized = {}
            for k, v in content.items():
                if k in ("timestamp", "created_at", "request_id", "post_num"):
                    continue
                normalized[k] = v
            try:
                raw_bytes = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
            except Exception:
                raw_bytes = str(normalized).encode("utf-8")
        elif isinstance(content, (str, bytes)):
            if isinstance(content, str):
                raw_bytes = content.strip().encode("utf-8")
            else:
                raw_bytes = content
        else:
            raw_bytes = str(content).encode("utf-8")

        return hashlib.sha256(raw_bytes).hexdigest()


# Global singleton instance
idempotency_tracker = IdempotencyTracker(default_ttl=30.0)
