import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

json_path = r"C:\Users\danat\Desktop\dvachbot\data\text_assets.json"
backup_path = json_path + ".bak3"

# Create a backup first
shutil.copyfile(json_path, backup_path)
print(f"Created backup at {backup_path}")

with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. Update CONTEXTUAL_REPLIES coder key
coder_key = r"\b(программ|код|кодинг|пк|комп|ноут|сервер|винда|линукс|python|js|питон|джава)\b"
replacements = {
    "Программирование — это искусство говорить компьютеру, что делать. А дебаггинг — это выяснение, почему он делает не то.":
        "Кодить — это тебе не хуем по клавиатуре стучать, хотя в твоем случае разницы нет.",
    "Проблема с ПК? Вероятно, дело в прокладке между креслом и монитором.":
        "Проблема с ПК? Дело в дегенерате за клавиатурой.",
    "Линукс? Уважаемо. Но помни: в мире есть два типа людей — те, кто бэкапит данные, и те, кто ЕЩЁ не бэкапит.":
        "Линуксоид детектед. Иди помойся, чучело.",
    "Твой код — как поэзия. Никто не понимает, зачем он нужен, но выглядит сложно.":
        "Твой говнокод выглядит так, будто его писал пьяный шимпанзе левой пяткой.",
    "Если хочешь, чтобы твой код работал, просто добавь больше комментариев. Компьютер не поймет, но люди оценят.":
        "Засунь свои комментарии себе в жопу, код от этого работать не начнет.",
    "Stack Overflow тебе в помощь, кожаный мешок.":
        "Иди нахуй, кожаный мешок.",
    "Проблема между стулом и монитором, очевидно же.":
        "Проблема в твоей тупой башке, очевидно же.",
    "Если дебаггинг — это процесс удаления багов, то программирование — это процесс их добавления.":
        "Дебажить твой говнокод — это как ковыряться в чужой блевотине. Противно, бессмысленно, но надо.",
    "Девяносто девять маленьких багов в коде, девяносто девять багов в коде, один исправляешь, сто двадцать заглавных багов в коде.":
        "Один говнокодер в чате, один говнокодер... Админ выдает бан, говнокодер плачет в подушку.",
    "Девяносто девять маленьких багов в коде, девяносто девять багов в коде, один исправляешь, сто двадцать семь маленьких багов в коде.":
        "Один говнокодер в чате, один говнокодер... Админ выдает бан, говнокодер плачет в подушку.",
    "Попробуй объяснить проблему резиновой уточке. Или мне. Эффект тот же.":
        "Объясни свою проблему своему отчиму. Может, он хотя бы ремня тебе даст за тупость.",
    "Чтобы решить эту проблему, тебе понадобится: кофе, бессонная ночь и капелька удачи.":
        "Чтобы решить эту проблему, тебе понадобится: удалить винду, закрыть рот и пойти нахуй.",
    "Каждый раз, когда ты задаешь вопрос, не прочитав документацию, где-то плачет один разработчик.":
        "Каждый раз, когда ты высераешь свой код в чат, Абу лично пробивает себе фейспалм.",
    "Это не баг. Это незадокументированная фича.":
        "Твой высер в чате — это не баг. Это просто признак лишней хромосомы.",
    "Проблема с железом? Попробуй пнуть системный блок. Иногда помогает.":
        "Проблема с железом? Попробуй выкинуть его в окно и прыгнуть следом.",
    "Прежде чем я отвечу, скажи: ты уже перезагружался?":
        "Прежде чем я пошлю тебя нахуй, скажи: ты уже пробовал перезагрузить свою единственную извилину?",
    "Твой код элегантен, как удар кирпичом по лицу. Но, возможно, сработает.":
        "Твой код элегантен, как удар кирпичом по яйцам. Переделывай.",
    "У тебя 'синий экран смерти'? Это просто твой ПК пытается косплеить цвет твоего настроения.":
        "У тебя синий экран смерти? Твой комп просто устал от твоего дегенеративного присутствия.",
    "Опять 'синий экран смерти'? Это твой комп намекает, что ему с тобой хуево.":
        "Опять синий экран? Выкинь это ведро на помойку.",
    "Segmentation fault. Это твой мозг пытается поделиться на ноль и умирает.":
        "Segmentation fault. Это твое ебало треснуло от натуги при попытке написать Hello World.",
    "Segmentation fault. Это твой мозг пытается разделиться на ноль.":
        "Segmentation fault. Это твое ебало треснуло от натуги при попытке написать Hello World.",
    "'Segmentation fault'. Это твой мозг пытается поделиться на ноль и умирает.":
        "Segmentation fault. Это твое ебало треснуло от натуги при попытке написать Hello World.",
    "Вижу null pointer exception. Это твоя жизнь пытается сослаться на смысл, а его нет.":
        "Вижу null pointer. Это твой батя пытается найти в тебе хоть какие-то признаки интеллекта, но там пусто."
}

if coder_key in data["CONTEXTUAL_REPLIES"]:
    phrases = data["CONTEXTUAL_REPLIES"][coder_key]
    for i, p in enumerate(phrases):
        if p in replacements:
            old_p = p
            phrases[i] = replacements[p]
            print(f"Replaced contextual reply: {old_p} -> {phrases[i]}")

# 2. Replace "био-юнит" and "юзай"
# ALBUM_EDUCATION_PHRASES.ru[18]
album_ru = data["ALBUM_EDUCATION_PHRASES"]["ru"]
for i, p in enumerate(album_ru):
    if "юзай её или свали!" in p:
        album_ru[i] = p.replace("юзай её или свали!", "используй её или свали!")
        print(f"Replaced in ALBUM_EDUCATION_PHRASES: {p} -> {album_ru[i]}")

# CONTEXTUAL_REPLIES for tiktok/reddit
tiktok_key = r"\b(тикток|реддит|пикабу|нормис|вк|инста|станкс|мемчики|хайп)\b"
if tiktok_key in data["CONTEXTUAL_REPLIES"]:
    tiktok_phrases = data["CONTEXTUAL_REPLIES"][tiktok_key]
    for i, p in enumerate(tiktok_phrases):
        if "не юзают" in p:
            tiktok_phrases[i] = p.replace("не юзают", "не употребляют")
            print(f"Replaced in tiktok key: {p} -> {tiktok_phrases[i]}")

# CONTEXTUAL_REPLIES for work
work_key = r"\b(работ[ауе]|завод|вкалыва|вкалываю|понедельник|начальник|офис)\b"
if work_key in data["CONTEXTUAL_REPLIES"]:
    work_phrases = data["CONTEXTUAL_REPLIES"][work_key]
    for i, p in enumerate(work_phrases):
        if "био-юнит" in p:
            work_phrases[i] = "Крепись, раб. Твой труд на заводе необходим, чтобы админ мог купить себе новые лоли-фигурки."
            print(f"Replaced bio-unit in work: {p} -> {work_phrases[i]}")

# CONTEXTUAL_REPLIES for greetings
greeting_key = r"\b(доброе утро|добрый день|добрый вечер|доброй ночи|спокойной ночи|привет всем|всем привет|всем пока|пока всем)\b"
if greeting_key in data["CONTEXTUAL_REPLIES"]:
    greeting_phrases = data["CONTEXTUAL_REPLIES"][greeting_key]
    for i, p in enumerate(greeting_phrases):
        if "био-юниты" in p:
            greeting_phrases[i] = "Доброе утро, стадо дегенератов. Конвейер деградации запущен."
            print(f"Replaced bio-unit in greeting: {p} -> {greeting_phrases[i]}")

# CONTEXTUAL_REPLIES for eating
eat_key = r"\b(поел|пое[мли]|жрать|хавать|хавчик|хрючево|еда|гречк[ауи]|макарошки|пельмен|сосиск|котлет|майонез|мазик|блюдо|ужин|завтрак|обед|доширак|кушац)\b"
if eat_key in data["CONTEXTUAL_REPLIES"]:
    eat_phrases = data["CONTEXTUAL_REPLIES"][eat_key]
    for i, p in enumerate(eat_phrases):
        if "био-юнита" in p:
            eat_phrases[i] = "Заправка очередного нищееба дешевым хрючевом прошла успешно. Хрюкни."
            print(f"Replaced bio-unit in eat: {p} -> {eat_phrases[i]}")


# 3. Clean up REACTION_NOTIFY_PHRASES['ru']['insult']
ru_insults = data["REACTION_NOTIFY_PHRASES"]["ru"]["insult"]
for i, p in enumerate(ru_insults):
    for term in ['инвалид', 'дегенерат', 'хуесос', 'пидорас', 'жид', 'хохол', 'москаль']:
        prefix_space = f" {term} "
        if p.startswith(prefix_space):
            emoji_map = {
                'инвалид': '♿',
                'дегенерат': '🧠',
                'хуесос': '👅',
                'пидорас': '🏳️‍🌈',
                'жид': '🕍',
                'хохол': '🐷',
                'москаль': '🪆'
            }
            clean_phrase = p[len(prefix_space):].strip()
            ru_insults[i] = f"{emoji_map[term]} {clean_phrase}"
            print(f"Cleaned prefix in ru insult: {p} -> {ru_insults[i]}")


# 4. Clean up and translate REACTION_NOTIFY_PHRASES['en']
data["REACTION_NOTIFY_PHRASES"]["en"]["political"] = [
    "🪆 Kremlinbots raided your post #{post_num}",
    "🇺🇦 Glory to Ukraine! (someone reacted to your post #{post_num})",
    "🏛️ Your post #{post_num} noticed in relevant organs",
    "🇷🇺 For post #{post_num} anon will get 15 rubles.",
    "🐷 Someone grunted at your post #{post_num}.",
    "ZOV Someone supported SVO on your post #{post_num}.",
    "Anon thinks you are libtard (post #{post_num}).",
    "Anon thinks you are vatnik (post #{post_num}).",
    "Anon thinks you are navalny supporter (post #{post_num}).",
    "Anon thinks you are putinist (post #{post_num}).",
    "🏳️‍🌈 Anon thinks you are gay-nazi (post #{post_num})."
]

data["REACTION_NOTIFY_PHRASES"]["en"]["symbolic"] = [
    "🏴‍☠️ Your post #{post_num} raised on pirate flag!",
    "♂️ Guys from gym appreciated your post #{post_num}",
    "🏴‍☠️ Yo-ho-ho and anon post! (on post #{post_num})",
    "♂️ Your post #{post_num} recognized truly manly",
    "☭ For post #{post_num} anon ready die for Stalin.",
    "Ⓐ Anarchy mother of order! (reaction to post #{post_num})",
    "⚛️ Your post #{post_num} is scientific breakthrough.",
    "☣️ This post #{post_num} is biological threat.",
    "☯️ Balance found in post #{post_num}.",
    "⛧ Satan approves post #{post_num}.",
    "Anon thinks you in world conspiracy (post #{post_num}).",
    "Anon thinks you are freemason (post #{post_num})."
]

data["REACTION_NOTIFY_PHRASES"]["en"]["insult"] = [
    "🐓 Anon thinks you are cock (post #{post_num})",
    "🐖 Someone grunted at your post #{post_num}",
    "🐓 Cock-a-doodle-doo! (reaction to post #{post_num})",
    "🐖 You were called pig (post #{post_num})",
    "🤡 You are clown. (reaction to post #{post_num})",
    "♿ Anon thinks you are invalid (post #{post_num}).",
    "🧠 Anon thinks you are degenerate (post #{post_num}).",
    "👅 Anon thinks you are cocksucker (post #{post_num}).",
    "🏳️‍🌈 Anon thinks you are faggot (post #{post_num}).",
    "🕍 Anon thinks you are kike (post #{post_num}).",
    "🐷 Anon thinks you are hohol (post #{post_num}).",
    "🪆 Anon thinks you are moskal (post #{post_num})."
]
print("Updated en block categories: political, symbolic, insult.")

# Save the updated data
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("Saved updated json to data/text_assets.json.")
