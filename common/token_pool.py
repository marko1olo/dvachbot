import os
import itertools
import random

class TokenRotator:
    def __init__(self, raw: str):
        # Разбиваем по запятой и чистим пробелы
        self.tokens = [t.strip() for t in raw.split(',') if t.strip()]
        self._iterator = itertools.cycle(self.tokens) if self.tokens else None

    def get_token(self) -> str | None:
        if not self._iterator:
            return None
        return next(self._iterator)

    def get_random(self) -> str | None:
        if not self.tokens:
            return None
        return random.choice(self.tokens)

# Инициализируем пулы
# В .env писать: HF_TOKENS=hf_1,hf_2,hf_3
hf_pool = TokenRotator(os.getenv("HF_TOKENS", ""))
# В .env писать: GROQ_API_KEYS=gsk_1,gsk_2
groq_pool = TokenRotator(os.getenv("GROQ_API_KEYS", ""))
class HfPairRotator:
    """
    Ротатор с умным чередованием (Interleaving).
    Цель: Равномерно распределить нагрузку по разным репозиториям.
    
    Порядок выдачи:
    Repo1-Token1 -> Repo2-Token1 -> ... -> Repo5-Token1 -> 
    Repo1-Token2 -> Repo2-Token2 -> ... -> Repo5-Token2 -> ...
    """
    def __init__(self):
        raw = os.getenv("HF_ACCOUNTS", "")
        
        # 1. Группируем токены по репозиториям
        # repo_map = { 'repo_id': ['token1', 'token2', 'token3'] }
        repo_map = {}
        repos_order = [] # Чтобы сохранить порядок появления (1, 2, 3, 4, 5)

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
                        repo_map[repo].append(token)
        
        # 2. Выстраиваем "идеальную очередь"
        self.pairs = []
        
        if repo_map:
            # Находим макс. количество токенов у одного репо (у тебя везде 3)
            max_tokens = max(len(tokens) for tokens in repo_map.values())
            
            # Проходим по индексам токенов (0, 1, 2...)
            for i in range(max_tokens):
                # Проходим по всем репозиториям (1, 2, 3, 4, 5)
                for repo in repos_order:
                    tokens = repo_map[repo]
                    # Если у этого репо есть токен под этим индексом - берем
                    if i < len(tokens):
                        self.pairs.append((tokens[i], repo))
        
        # Логгируем для проверки (в консоль при старте)
        # print(f"HF Rotator loaded {len(self.pairs)} pairs in interleaved order.")
        
        self._iterator = itertools.cycle(self.pairs) if self.pairs else None

    def get_pair(self) -> tuple[str, str] | tuple[None, None]:
        """Возвращает (token, repo_id) или (None, None)"""
        if not self._iterator:
            return None, None
        return next(self._iterator)

# Инициализируем ротатор пар
hf_accounts = HfPairRotator()
