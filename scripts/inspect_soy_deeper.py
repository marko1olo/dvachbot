import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/text_assets.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sections = [
    'EARNING_NOTIFICATIONS',
    'REFERRAL_BONUS_MESSAGES',
    'VERIFICATION_SUCCESS_MESSAGES',
    'VERIFICATION_REQUIRED_MESSAGES',
    'MOTIVATIONAL_MESSAGES',
    'SITE_PROMO_PHRASES',
    'POLL_CREATION_SUCCESS_PHRASES',
    'ANIME_CMD_SUCCESS_PHRASES',
    'ANIME_CMD_SEARCHING_PHRASES'
]

for s in sections:
    print(f"==================== {s} =====================")
    val = data.get(s)
    if isinstance(val, dict):
        for k, v in val.items():
            print(f"  {k}: {v}")
    elif isinstance(val, list):
        for i, item in enumerate(val):
            print(f"  [{i}]: {repr(item)}")
    print()
