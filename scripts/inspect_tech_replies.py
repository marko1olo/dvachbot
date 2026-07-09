import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/text_assets.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

tech_keys = [
    r'\b(код|скрипт|пайтон|python|си\+\+|с\+\+|джава|js|программист|кодер|айти)\b',
    r'\b(программ|код|кодинг|пк|комп|ноут|сервер|винда|линукс|python|js|питон|джава)\b',
    r'\b(прогресс|технологии|киберпанк|ии|нейросеть|робот|будущее|сингулярность)\b',
    r'\b(chatgpt|гпт|gpt|claude|llama|midjourney|нейросеть|нейронка|ии|нейрокал|нейросетка)\b',
    r'\b(ты[\s-]живой|кто[\s-]ты|бот[\s-]умный|чувства|сознание|машина|код|программа)\b'
]

for pat in tech_keys:
    # Find matching key
    matched_key = None
    for k in data['CONTEXTUAL_REPLIES'].keys():
        if k == pat:
            matched_key = k
            break
    if matched_key:
        print(f"==================== KEY: {matched_key} ====================")
        for i, item in enumerate(data['CONTEXTUAL_REPLIES'][matched_key]):
            print(f"  [{i}]: {repr(item)}")
        print()
