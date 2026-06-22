import re
import os

def clean_file(filename):
    if not os.path.exists(filename):
        return
        
    with open(filename, 'r', encoding='utf-8') as f:
        code = f.read()

    replacements = {
        r"❌ ❌ Доступ закрыт. Съеби..": r"❌ Доступ закрыт. Съеби.",
        r"ℹ️ ❌ Такого слова нет в списке.": r"❌ Такого слова нет в списке.",
        r"❌ ❌ Ошибка БД. Абу споткнулся о сервер.": r"❌ Ошибка БД. Абу споткнулся о сервер.",
        r"Недостаточно текста за последние 24 часа для генерации облака слов.": r"❌ Хуй там плавал, а не облако слов. Вы нафлудили слишком мало текста за сутки.",
        r"⚠️ Telegram отклонил запрос. Попробуй ещё раз.": r"⚠️ Телега послала нахуй твой запрос. Пробуй снова.",
        r"⏳ <i>Генерирую 10 графиков статистики \(это может занять пару секунд\)...</i>": r"⏳ <i>Рисую 10 графиков вашей деградации (погоди пару секунд)...</i>",
        r"❌ Не удалось собрать данные для статистики.": r"❌ Хуй там плавал, стату собрать не вышло."
    }

    for old, new in replacements.items():
        code = re.sub(old, new, code)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(code)

clean_file('main.py')
clean_file('site_tgach/main.py')
clean_file('Dubsite_tgach/main.py')
clean_file('periodic_publisher.py')
print("Leftover patches applied")
