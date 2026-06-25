import random

def _get_random_header_prefix(lang: str = 'ru') -> str:

    rand_prefix = random.random()
    if lang == 'en':
        if rand_prefix < 0.005: return "### ADMIN ### "
        if rand_prefix < 0.008: return "Me - "
        if rand_prefix < 0.01: return "Faggot - "
        if rand_prefix < 0.012: return "### DEGENERATE ### "
        if rand_prefix < 0.016: return "Biden - "
        if rand_prefix < 0.021: return "EMPEROR CONAN - "
        if rand_prefix < 0.023: return "### TRANNY ### "
        if rand_prefix < 0.05: return "Anon - " # Чаще для английского
        return ""
    if lang == 'jp':
        if rand_prefix < 0.005: return "### 管理人 ### " # Kanrinin (Admin)
        if rand_prefix < 0.008: return "俺 - " # Ore (Me)
        if rand_prefix < 0.01: return "ホモ - " # Homo (Faggot)
        if rand_prefix < 0.012: return "### 変質者 ### " # Henshitsu-sha (Degenerate)
        if rand_prefix < 0.016: return "岸田 - " # Kishida (PM context)
        if rand_prefix < 0.021: return "コナン皇帝 - " # Emperor Conan
        if rand_prefix < 0.023: return "### オカマ ### " # Okama (Tranny)
        if rand_prefix < 0.030: return "お前 - " # Omae (You)
        if rand_prefix < 0.040: return "暇人 - " # Himajin (Bitard/Neet)
        if rand_prefix < 0.08: return "名無し - " # Nanashi (Anon) - самый частый
        return ""
    if rand_prefix < 0.005: return "### АДМИН ### "
    if rand_prefix < 0.008: return "Абу - "
    if rand_prefix < 0.01: return "Пидор - "
    if rand_prefix < 0.012: return "### ДЖУЛУП ### "
    if rand_prefix < 0.014: return "### Хуесос ### "
    if rand_prefix < 0.016: return "Пыня - "
    if rand_prefix < 0.018: return "Нариман Намазов - "
    if rand_prefix < 0.021: return "ИМПЕРАТОР КОНАН - "
    if rand_prefix < 0.023: return "Антон Бабкин - "
    if rand_prefix < 0.025: return "НАРИМАН НАМАЗОВ - "
    if rand_prefix < 0.027: return "ПУТИН - "
    if rand_prefix < 0.028: return "Гей - "
    if rand_prefix < 0.030: return "Анархист - "
    if rand_prefix < 0.033: return "Имбецил - "
    if rand_prefix < 0.035: return "### ЧМО ### "
    if rand_prefix < 0.037: return "### ОНАНИСТ ### "
    if rand_prefix < 0.040: return "### ЧЕЧЕНЕЦ ### "
    if rand_prefix < 0.042: return "АААААААА - "
    if rand_prefix < 0.044: return "### Аниме девочка ### "
    if rand_prefix < 0.046: return "ChatGPT 5.4 - "
    if rand_prefix < 0.048: return "Безумец - "
    if rand_prefix < 0.050: return "Битард - "
    if rand_prefix < 0.052: return "Мегумин - "
    if rand_prefix < 0.054: return "Гопник - "
    if rand_prefix < 0.056: return "Шизик - "
    if rand_prefix < 0.058: return "Джефри Эпштейн - "
    if rand_prefix < 0.060: return "Максим Тесак - "
    if rand_prefix < 0.062: return "Навальный - "
    if rand_prefix < 0.064: return "Рамзанка дыров - "
    if rand_prefix < 0.066: return "СВОШНИК - "
    if rand_prefix < 0.068: return "Герой Украины - "
    if rand_prefix < 0.070: return "Claude Opus 4.6 - "
    if rand_prefix < 0.076: return "Администратор - "
    if rand_prefix < 0.08: return "Админ - "
    if rand_prefix < 0.085: return "Модератор - "
    if rand_prefix < 0.1: return "Анон - "
    if rand_prefix < 0.115: return "Анонимус - "
    if rand_prefix < 0.13: return "Анонимный пользователь - "
    return ""
