# tgach_bot/token_generator.py
# выполняет генерацию уникальных токенов для API и других нужд
import random
import secrets
import hashlib

# --- Списки слов, сгруппированные по грамматическому роду ---

# Мужской род (какой? кто?/что?)
MALE_ADJECTIVES = [
    "Анонимный", "Сычующий", "Ламповый", "Зеленый", "Толстый", "Русский", "Либеральный",
    "Школьный", "Модопроблемный", "Капчующий", "Двачующий", "Ночной",
    "Унылый", "Эпичный", "Редкий", "Обычный", "Злой", "Убогий", "Опущенный", 
]
MALE_NOUNS = [
    "Битард", "Хиккан", "Абу", "Омеган", "Тред", "Ерохин", "Админ", "Сосач", "Тгач", "Ежач", "Хохол", "Пыня", 
    "Ньюфаг", "Анонимус", "Бамп", "Мочер", "Кун", "Оператор", "Нариман", "Петух", "Скуф", "Зумер", "Порридж", "Скуф", "Конан",
]

# Женский род (какая? кто?/что?)
FEMALE_ADJECTIVES = [
    "Анонимная", "Ламповая", "Редкая", "Обычная", "Грустная",
    "Печальная", "Няшная", "Ночная", "Злая", "Милая", "Красивая", "Толстая",
]
FEMALE_NOUNS = [
    "Тян", "Сажа", "Капча", "Вайфу", "Дурка", "Сосака", "Мразь",
    "Шинобу", "Паста", "Алиса", "Сырно", "Цундере", "Годнота", "Псина",
]

# Средний род (какое? что?)
NEUTER_ADJECTIVES = [
    "Анонимное", "Ламповое", "Редкое", "Обычное", "Типичное", "Необычное",
    "Унылое", "Зеленое", "Толстое", "Печальное", "Эпичное", "Бесконечное", 
]
NEUTER_NOUNS = [
    "Обыдление", "Двачевание", "Пояснение", "Быдло", "Говно",
    "Лето", "Аниме", "Призвание", "Сосание", "Лицо", "Чмо", "Говнище"
]

# Объединяем все группы в один список для случайного выбора
WORD_GROUPS = [
    (MALE_ADJECTIVES, MALE_NOUNS),
    (FEMALE_ADJECTIVES, FEMALE_NOUNS),
    (NEUTER_ADJECTIVES, NEUTER_NOUNS),
]

async def generate_unique_token(db_check_func) -> str:
    """
    Генерирует уникальный, читаемый и грамматически согласованный по роду токен.
    """
    max_attempts = 10
    for _ in range(max_attempts):
        adjectives, nouns = random.choice(WORD_GROUPS)
        adjective = random.choice(adjectives)
        noun = random.choice(nouns)
        number = secrets.randbelow(90000) + 10000

        token = f"{adjective} {noun} {number}"

        if not await db_check_func(token):
            return token
            
    return f"{token}-{secrets.token_hex(2)}"

def generate_negative_id(token: str) -> int:
    hash_val = hashlib.sha256(token.encode()).hexdigest()
    val = int(hash_val[:8], 16)
    return -(val % 2147483647) - 1
