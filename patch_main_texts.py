import re

filename = 'main.py'

with open(filename, 'r', encoding='utf-8') as f:
    code = f.read()

replacements = {
    r'final = f"✅ Пост #\{post_num\} закреплен \(Успешно: \{count_success\}\)\.\\nНовые пользователи тоже увидят его\."': 
        r'final = f"✅ Пост #{post_num} прибит гвоздями (Разослано: {count_success} анонам).\nНьюфаги тоже увидят."',
    
    r'confirm = "Тред успешно удалён, пользователи переведены на главную\."': 
        r'confirm = "Тред снесен нахуй, всех выкинуло на главную."',
        
    r'st_msg = await message\.answer\(f"✅ Успешно удалено у \{success_count\} пользователей\."\)': 
        r'st_msg = await message.answer(f"✅ Выпилено у {success_count} анонов.")',
        
    r'response_text = "✅ База данных успешно сохранена в GitHub\." if success else "❌ Ошибка при создании бэкапа\. См\. логи\."': 
        r'response_text = "✅ Бэкап залит на гитхаб." if success else "❌ Проебали бэкап. См. логи."',
        
    r'error_text = "Прикрепление медиагрупп к опросам не поддерживается\. Пожалуйста, ответьте на одно конкретное фото или видео\."': 
        r'error_text = "Опросы с медиагруппами — хуйня нерабочая. Отвечай на одну конкретную картинку или видос."'
}

for old, new in replacements.items():
    code = re.sub(old, new, code)

with open(filename, 'w', encoding='utf-8') as f:
    f.write(code)

print("main.py text patched")
