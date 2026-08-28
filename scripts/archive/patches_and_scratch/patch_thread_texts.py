import re

filename = 'thread_texts.py'

with open(filename, 'r', encoding='utf-8') as f:
    code = f.read()

replacements = {
    r'"✅ Тред «<b>\{title\}</b>» успешно создан\. Ждем экспертов\.",': r'"✅ Тред «<b>{title}</b>» высран. Ждем набега дебилов.",',
    r'"Ты успешно вкатился в тред «<b>\{title\}</b>»\.\\n\\n🚪 Надоест - жми /leave\.",': r'"Ты вкатился в тред «<b>{title}</b>».\n\n🚪 Надоест эта хуйня - жми /leave.",',
    r'"🔇 Успешно заткнул\. Срок: \{duration\} минут\.",': r'"🔇 Заткнул уебка. Срок: {duration} минут.",'
}

for old, new in replacements.items():
    code = re.sub(old, new, code)

with open(filename, 'w', encoding='utf-8') as f:
    f.write(code)

print("thread_texts.py patched")
