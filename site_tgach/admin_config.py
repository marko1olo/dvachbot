# Список Telegram ID администраторов, которым будут доступны
# функции модерации на сайте.
try:
    from common.config import ADMIN_IDS as CONFIG_ADMIN_IDS
    ADMIN_IDS = CONFIG_ADMIN_IDS if CONFIG_ADMIN_IDS else {7716348189, 1890028643}
except ImportError:
    ADMIN_IDS = {
        7716348189,
        1890028643,
    }