with open("site_tgach/admin_config.py", "r") as f:
    content = f.read()

new_content = """import os

# Список Telegram ID администраторов, которым будут доступны
# функции модерации на сайте.
try:
    from common.config import ADMIN_IDS as CONFIG_ADMIN_IDS
    ADMIN_IDS = CONFIG_ADMIN_IDS
except ImportError:
    admin_env = os.getenv("ADMINS", "")
    ADMIN_IDS = {int(x.strip()) for x in admin_env.split(",") if x.strip().isdigit()}
"""

with open("site_tgach/admin_config.py", "w") as f:
    f.write(new_content)
