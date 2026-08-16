import os
import time
import random
import threading
import asyncio
from pathlib import Path


def _clean_and_dedup_keys(*sources: str | list | tuple | set | None) -> list[str]:
    """
    Чистит, нормализует и строго дедуплицирует список API-ключей,
    сохраняя порядок первого появления.
    Удаляет лишние пробелы, кавычки и комментарии.
    """
    seen = set()
    result = []
    for src in sources:
        if not src:
            continue
        if isinstance(src, str):
            items = src.split(',')
        elif isinstance(src, (list, tuple, set)):
            items = src
        else:
            continue
        for item in items:
            k = str(item).strip().strip('"\'')
            if k and k not in seen and not k.startswith('#'):
                seen.add(k)
                result.append(k)
    return result


def _load_env_keys(env_vars: list[str], extra_files: list[str] = None) -> list[str]:
    """
    Загружает ключи из указанных файлов и переменных окружения, дедуплицируя их.
    """
    collected = []
    if extra_files:
        project_root = Path(__file__).resolve().parent.parent
        for fname in extra_files:
            fpath = project_root / fname
            if fpath.is_file():
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            for var in env_vars:
                                if line.startswith(f"{var}="):
                                    val = line.split("=", 1)[1].strip()
                                    collected.append(val)
                except Exception:
                    pass

    for var in env_vars:
        val = os.getenv(var, "")
        if val:
            collected.append(val)

    return _clean_and_dedup_keys(*collected)


class TokenRotator:
    """
    Потокобезопасный и асинхронный ротатор API-ключей (Round-Robin) с:
    - строгой дедупликацией
    - защитой от спама (минимальный интервал между вызовами одного и того же ключа)
    - временным штрафом при ошибках (429 Rate Limit)
    - перманентным баном при 401/403
    """
    def __init__(self, raw: str | list[str] = "", min_interval: float = 2.5, name: str = "TokenPool"):
        self.name = name
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self.tokens: list[str] = _clean_and_dedup_keys(raw)
        self._index: int = 0
        self._last_used: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._banned: set[str] = set()

    def set_tokens(self, raw: str | list[str]):
        with self._lock:
            self.tokens = _clean_and_dedup_keys(raw)
            if self._index >= len(self.tokens):
                self._index = 0

    def add_token(self, token: str):
        with self._lock:
            clean = token.strip().strip('"\'')
            if clean and clean not in self.tokens and clean not in self._banned:
                self.tokens.append(clean)

    def remove_token(self, token: str):
        with self._lock:
            if token in self.tokens:
                self.tokens.remove(token)
            self._banned.add(token)
            if self._index >= len(self.tokens):
                self._index = 0

    def ban_token(self, token: str):
        self.remove_token(token)

    def penalize_token(self, token: str, duration: float = 60.0):
        """Накладывает штрафной кулдаун на ключ (например, при 429)."""
        with self._lock:
            self._cooldown_until[token] = time.time() + duration

    def get_token(self) -> str | None:
        """
        Классический честный Round-Robin выбор ключа.
        Пропускает забаненные токены.
        """
        with self._lock:
            active = [t for t in self.tokens if t not in self._banned]
            if not active:
                return None
            token = active[self._index % len(active)]
            self._index = (self._index + 1) % len(active)
            self._last_used[token] = time.time()
            return token

    def get_random(self) -> str | None:
        with self._lock:
            active = [t for t in self.tokens if t not in self._banned]
            if not active:
                return None
            return random.choice(active)

    def get_all_active_tokens(self) -> list[str]:
        """Возвращает все активные дедуплицированные токены в порядке очереди."""
        with self._lock:
            active = [t for t in self.tokens if t not in self._banned]
            if not active:
                return []
            idx = self._index % len(active)
            return active[idx:] + active[:idx]

    async def acquire_token_async(self, min_interval: float | None = None, max_wait: float = 15.0) -> tuple[str | None, float]:
        """
        Асинхронный умный выбор токена:
        1. Ищет токен, у которого истек штраф (429) и прошло не менее min_interval секунд с последнего запроса.
        2. Если все токены сейчас 'отдыхают', вычисляет минимальную необходимую паузу и делает sleep.
        3. Возвращает (выбранный_токен, время_ожидания_в_секундах).
        """
        interval = min_interval if min_interval is not None else self.min_interval
        loop = asyncio.get_running_loop()
        
        while True:
            selected_token = None
            wait_time = 0.0
            now = time.time()
            
            with self._lock:
                active = [t for t in self.tokens if t not in self._banned]
                if not active:
                    return None, 0.0

                # 1. Поиск готового токена без ожидания
                for i in range(len(active)):
                    idx = (self._index + i) % len(active)
                    tok = active[idx]
                    cd = self._cooldown_until.get(tok, 0.0)
                    last_u = self._last_used.get(tok, 0.0)
                    
                    if now >= cd and (now - last_u) >= interval:
                        selected_token = tok
                        self._index = (idx + 1) % len(active)
                        self._last_used[tok] = now
                        break

                # 2. Если все заняты/остывают — находим токен с минимальным временем ожидания
                if not selected_token:
                    min_delay = float('inf')
                    best_tok = None
                    best_idx = 0
                    for i in range(len(active)):
                        idx = (self._index + i) % len(active)
                        tok = active[idx]
                        cd = self._cooldown_until.get(tok, 0.0)
                        last_u = self._last_used.get(tok, 0.0)
                        
                        delay_cd = max(0.0, cd - now)
                        delay_rate = max(0.0, (last_u + interval) - now)
                        delay = max(delay_cd, delay_rate)
                        
                        if delay < min_delay:
                            min_delay = delay
                            best_tok = tok
                            best_idx = idx

                    if best_tok and min_delay <= max_wait:
                        selected_token = best_tok
                        wait_time = min_delay
                        self._index = (best_idx + 1) % len(active)
                        self._last_used[best_tok] = now + wait_time
                    else:
                        return None, 0.0

            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            return selected_token, wait_time


class HfPairRotator:
    """
    Ротатор с умным чередованием (Interleaving).
    Равномерно распределяет нагрузку по разным репозиториям.
    
    Порядок выдачи:
    Repo1-Token1 -> Repo2-Token1 -> ... -> RepoN-Token1 -> 
    Repo1-Token2 -> Repo2-Token2 -> ... -> RepoN-Token2
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._reload()

    def _reload(self):
        raw = os.getenv("HF_ACCOUNTS", "")
        repo_map = {}
        repos_order = []

        if raw:
            items = raw.split(',')
            for item in items:
                item = item.strip()
                if ':' in item:
                    parts = item.split(':', 1)
                    token = parts[0].strip()
                    repo = parts[1].strip()
                    
                    if token and repo:
                        if repo not in repo_map:
                            repo_map[repo] = []
                            repos_order.append(repo)
                        if token not in repo_map[repo]:
                            repo_map[repo].append(token)
        
        self.pairs = []
        if repo_map:
            max_tokens = max(len(tokens) for tokens in repo_map.values())
            for i in range(max_tokens):
                for repo in repos_order:
                    tokens = repo_map[repo]
                    if i < len(tokens):
                        self.pairs.append((tokens[i], repo))
        
        self._index = 0

    def get_pair(self) -> tuple[str, str] | tuple[None, None]:
        """Возвращает (token, repo_id) или (None, None)"""
        with self._lock:
            if not self.pairs:
                return None, None
            pair = self.pairs[self._index % len(self.pairs)]
            self._index = (self._index + 1) % len(self.pairs)
            return pair


# === ГЛОБАЛЬНЫЕ ИНИЦИАЛИЗИРОВАННЫЕ ПУЛЫ ===

hf_pool = TokenRotator(
    raw=_load_env_keys(["HF_TOKENS", "HF_TOKEN"], extra_files=[".env"]),
    min_interval=2.0,
    name="HuggingFacePool"
)

groq_pool = TokenRotator(
    raw=_load_env_keys(["GROQ_API_KEYS", "GROQ_KEYS", "GROQ_API_KEY"], extra_files=[".env", ".envgroq"]),
    min_interval=2.5,
    name="GroqPool"
)

google_pool = TokenRotator(
    raw=_load_env_keys(
        ["GOOGLE_API_KEYS", "GOOGLE_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"],
        extra_files=[".envgoogle", ".env"]
    ),
    min_interval=3.0,
    name="GoogleGeminiPool"
)

hf_accounts = HfPairRotator()
