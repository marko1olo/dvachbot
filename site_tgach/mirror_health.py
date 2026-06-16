import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger("mirror_health")

HF_LOCKED_COOLDOWN_SECONDS = int(os.getenv("HF_LOCKED_COOLDOWN_SECONDS", str(6 * 60 * 60)))
HF_HEALTH_STATE_PATH = Path(
    os.getenv("HF_HEALTH_STATE_PATH", os.path.join(os.getcwd(), "data", "mirror_health.json"))
)

_LOCK = threading.Lock()
_STATE = {
    "hf_disabled_until": {},
    "hf_disabled_reason": {},
}


def _load_state() -> None:
    global _STATE
    try:
        if not HF_HEALTH_STATE_PATH.exists():
            return
        data = json.loads(HF_HEALTH_STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _STATE["hf_disabled_until"] = dict(data.get("hf_disabled_until") or {})
            _STATE["hf_disabled_reason"] = dict(data.get("hf_disabled_reason") or {})
    except Exception as exc:
        logger.warning("Failed to load mirror health state: %s", exc)


def _save_state_locked() -> None:
    try:
        HF_HEALTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_STATE, ensure_ascii=True, separators=(",", ":"))
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(HF_HEALTH_STATE_PATH.parent),
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        os.replace(tmp_path, HF_HEALTH_STATE_PATH)
    except Exception as exc:
        logger.warning("Failed to save mirror health state: %s", exc)


def _is_disabled_by_env() -> bool:
    return os.getenv("HF_MIRRORS_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_locked_error(error: object) -> bool:
    text = str(error).lower()
    if "locked out" in text and "hugging face account" in text:
        return True
    if "403" in text and "violation of our terms" in text:
        return True
    if "403 forbidden" in text and "huggingface.co/api/datasets" in text:
        return True
    return False


def mark_hf_upload_failure(error: object, repo: str | None = None) -> bool:
    if not repo or not _is_locked_error(error):
        return False

    until = time.time() + HF_LOCKED_COOLDOWN_SECONDS
    with _LOCK:
        _STATE["hf_disabled_until"][repo] = until
        _STATE["hf_disabled_reason"][repo] = str(error)[:500]
        _save_state_locked()

    logger.error("HF repo disabled for %.0fs after locked/403 response: %s", HF_LOCKED_COOLDOWN_SECONDS, repo)
    return True


def clear_hf_failure(repo: str | None) -> None:
    if not repo:
        return
    with _LOCK:
        changed = False
        if repo in _STATE["hf_disabled_until"]:
            _STATE["hf_disabled_until"].pop(repo, None)
            changed = True
        if repo in _STATE["hf_disabled_reason"]:
            _STATE["hf_disabled_reason"].pop(repo, None)
            changed = True
        if changed:
            _save_state_locked()


def is_hf_repo_available(repo: str | None) -> bool:
    if _is_disabled_by_env():
        return False
    if not repo:
        return False
    with _LOCK:
        disabled_until = float(_STATE["hf_disabled_until"].get(repo) or 0)
    return disabled_until <= time.time()


def get_configured_hf_repos() -> set[str]:
    repos = set()
    for account in os.getenv("HF_ACCOUNTS", "").split(","):
        account = account.strip()
        if ":" not in account:
            continue
        repo = account.split(":", 1)[1].strip()
        if repo:
            repos.add(repo)
    return repos


def has_available_hf_repo() -> bool:
    repos = get_configured_hf_repos()
    if not repos:
        return False
    return any(is_hf_repo_available(repo) for repo in repos)


def is_hf_link_allowed(url: str | None, valid_repos: set[str]) -> bool:
    if not url:
        return False
    if not valid_repos:
        return not _is_disabled_by_env()

    for repo in valid_repos:
        if repo in url:
            return is_hf_repo_available(repo)
    return False


def get_hf_health_snapshot() -> dict:
    now = time.time()
    with _LOCK:
        return {
            repo: {
                "disabled_for_seconds": max(0, int(float(until) - now)),
                "reason": _STATE["hf_disabled_reason"].get(repo, ""),
            }
            for repo, until in _STATE["hf_disabled_until"].items()
            if float(until) > now
        }


_load_state()
