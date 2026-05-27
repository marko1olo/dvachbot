# common/board_config.py
import os
from dotenv import load_dotenv
from pathlib import Path

project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- НАСТРОЙКИ ---
ENABLE_MULTILANG = False 
CIS_COUNTRY_CODES = {'RU', 'UA', 'BY', 'KZ', 'KG', 'TJ', 'UZ', 'AM', 'AZ', 'MD', 'TM'}

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")
BOT_TOKEN = os.getenv("BOT_TOKEN") # Главный бот (обычно для /b/ или уведомлений)
FILE_UPLOADER_BOT_TOKEN = os.getenv("FILE_UPLOADER_BOT_TOKEN")
BOT_USERNAME = "dvach_chatbot"

# Хелпер для безопасного получения ID каналов
def parse_channel_id(val):
    return int(val) if val and val.strip().lstrip('-').isdigit() else None
SHADOW_CHANNEL_ID = parse_channel_id(os.getenv("SHADOW_CHANNEL_ID"))
FILE_STORAGE_CHANNEL_ID = parse_channel_id(os.getenv("FILE_STORAGE_CHANNEL_ID"))
THREAD_MEDIA_CHANNEL_ID = parse_channel_id(os.getenv("THREAD_MEDIA_CHANNEL_ID"))

# Хелпер для получения токена (возвращает None, если пусто)
def parse_token(val):
    return val if val and val.strip() else None

# Хелпер для админов
def parse_admins(raw):
    return {int(y) for x in raw.split(",") if (y := x.strip()).isdigit()}

BOARD_CONFIG = {
    # === ОСНОВА (popular) ===
    'b': {
        "name": "/b/",
        "category": "popular",
        "description": {"ru": "Свободное общение", "en": "General", "jp": "雑談"},
        "color1": "#e67e22", "color2": "#2ecc71",
        "username": "@dvach_chatbot", "token": parse_token(os.getenv("BOT_TOKEN")), "admins": parse_admins(os.getenv("ADMINS", ""))
    },
    'a': {
        "name": "/a/",
        "category": "popular",
        "description": {"ru": "Аниме и Манга", "en": "Anime", "jp": "アニメ"},
        "color1": "#9b59b6", "color2": "#f1c40f",
        "username": "@dvach_a_chatbot", "token": parse_token(os.getenv("A_BOT_TOKEN")), "admins": parse_admins(os.getenv("A_ADMINS", ""))
    },
    'po': {
        "name": "/po/",
        "category": "popular",
        "description": {"ru": "Политика", "en": "Politics", "jp": "政治"},
        "color1": "#c0392b", "color2": "#34495e",
        "username": "@dvach_po_chatbot", "token": parse_token(os.getenv("PO_BOT_TOKEN")), "admins": parse_admins(os.getenv("PO_ADMINS", ""))
    },

    # === БИОПРОБЛЕМЫ (bio) ===
    'soc': {
        "name": "/soc/",
        "category": "bio",
        "description": {"ru": "Знакомства", "en": "Social", "jp": "出会い"},
        "color1": "#e84393", "color2": "#fd79a8",
        "username": "@tgach_soc_bot", "token": parse_token(os.getenv("SOC_BOT_TOKEN")), "admins": parse_admins(os.getenv("ADMINS", ""))
    },
    'sex': {
        "name": "/sex/",
        "category": "bio",
        "description": {"ru": "Секс", "en": "Sex", "jp": "性"},
        "color1": "#e91e63", "color2": "#2c3e50",
        "username": "@dvach_sex_chatbot", "token": parse_token(os.getenv("SEX_BOT_TOKEN")), "admins": parse_admins(os.getenv("SEX_ADMINS", ""))
    },
    'h': {
        "name": "/h/",
        "category": "bio",
        "description": {"ru": "Хентай", "en": "Hentai", "jp": "変態"},
        "color1": "#fd79a8", "color2": "#2d3436",
        "username": "@tgach_h_bot", "token": parse_token(os.getenv("H_BOT_TOKEN")), "admins": parse_admins(os.getenv("H_ADMINS", ""))
    },
    'bunker': {
        "name": "/bunker/",
        "category": "bio",
        "description": {"ru": "Убежище", "en": "Bunker", "jp": "避難所"},
        "color1": "#2d3436", "color2": "#636e72",
        "username": "@tgach_bunker_bot", "token": parse_token(os.getenv("BUNKER_BOT_TOKEN")), "admins": parse_admins(os.getenv("ADMINS", ""))
    },

    # === ТЕМАТИКА (thematic) ===
    'fit': {
        "name": "/fit/",
        "category": "thematic",
        "description": {"ru": "Фитнес", "en": "Fitness", "jp": "健康"},
        "color1": "#3498db", "color2": "#ecf0f1",
        "username": "@tgach_fit_bot", "token": parse_token(os.getenv("FIT_BOT_TOKEN")), "admins": parse_admins(os.getenv("FIT_ADMINS", ""))
    },
    'me': {
        "name": "/me/",
        "category": "thematic",
        "description": {"ru": "Медицина", "en": "Medicine", "jp": "医学"},
        "color1": "#00b894", "color2": "#ffffff",
        "username": "@tgach_me_bot", "token": parse_token(os.getenv("ME_BOT_TOKEN")), "admins": parse_admins(os.getenv("ME_ADMINS", ""))
    },
    'tech': {
        "name": "/tech/",
        "category": "thematic",
        "description": {"ru": "Технологии", "en": "Tech", "jp": "技術"},
        "color1": "#2c3e50", "color2": "#2ecc71",
        "username": "@tgach_tech_bot", "token": parse_token(os.getenv("TECH_BOT_TOKEN")), "admins": parse_admins(os.getenv("G_ADMINS", ""))
    },
    'tv': {
        "name": "/tv/",
        "category": "thematic",
        "description": {"ru": "Кино и ТВ", "en": "TV", "jp": "映画"},
        "color1": "#2980b9", "color2": "#bdc3c7",
        "username": "@tgach_tv_bot", "token": parse_token(os.getenv("TV_BOT_TOKEN")), "admins": parse_admins(os.getenv("TV_ADMINS", ""))
    },
    'v': {
        "name": "/v/",
        "category": "thematic",
        "description": {"ru": "Видеоигры", "en": "Video Games", "jp": "ゲーム"},
        "color1": "#27ae60", "color2": "#2c3e50",
        "username": "@tgach_v_bot", "token": parse_token(os.getenv("V_BOT_TOKEN")), "admins": parse_admins(os.getenv("V_ADMINS", ""))
    },
    'vg': {
        "name": "/vg/",
        "category": "thematic",
        "description": {"ru": "Геймдев", "en": "VG Generals", "jp": "業界"},
        "color1": "#16a085", "color2": "#2c3e50",
        "username": "@dvach_vg_chatbot", "token": parse_token(os.getenv("VG_BOT_TOKEN")), "admins": parse_admins(os.getenv("VG_ADMINS", ""))
    },
    'sci': {
        "name": "/sci/",
        "category": "thematic",
        "description": {"ru": "Наука", "en": "Science", "jp": "科学"},
        "color1": "#0984e3", "color2": "#dfe6e9",
        "username": "@tgach_sci_bot", "token": parse_token(os.getenv("SCI_BOT_TOKEN")), "admins": parse_admins(os.getenv("SCI_ADMINS", ""))
    },
    'wh40k': {
        "name": "/wh40k/",
        "category": "thematic",
        "description": {"ru": "Warhammer", "en": "Warhammer", "jp": "WH40K"},
        "color1": "#2c3e50", "color2": "#c0392b",
        "username": "@tgach_wh40k_bot", "token": parse_token(os.getenv("WH40K_BOT_TOKEN")), "admins": parse_admins(os.getenv("ADMINS", ""))
    },
    'biz': {
        "name": "/biz/",
        "category": "thematic",
        "description": {"ru": "Бизнес", "en": "Business", "jp": "ビジネス"},
        "color1": "#f39c12", "color2": "#2c3e50",
        "username": "@tgach_biz_bot", "token": parse_token(os.getenv("BIZ_BOT_TOKEN")), "admins": parse_admins(os.getenv("BIZ_ADMINS", ""))
    },
    'mu': {
        "name": "/mu/",
        "category": "thematic",
        "description": {"ru": "Музыка", "en": "Music", "jp": "音楽"},
        "color1": "#d35400", "color2": "#ecf0f1",
        "username": "@tgach_mu_bot", "token": parse_token(os.getenv("MU_BOT_TOKEN")), "admins": parse_admins(os.getenv("MU_ADMINS", ""))
    },
    'fa': {
        "name": "/fa/",
        "category": "thematic",
        "description": {"ru": "Мода", "en": "Fashion", "jp": "ファッション"},
        "color1": "#7f8c8d", "color2": "#000000",
        "username": "@tgach_fa_bot", "token": parse_token(os.getenv("FA_BOT_TOKEN")), "admins": parse_admins(os.getenv("FA_ADMINS", ""))
    },
    'x': {
        "name": "/x/",
        "category": "thematic",
        "description": {"ru": "Мистика", "en": "Paranormal", "jp": "オカルト"},
        "color1": "#000000", "color2": "#1abc9c",
        "username": "@tgach_x_bot", "token": parse_token(os.getenv("X_BOT_TOKEN")), "admins": parse_admins(os.getenv("X_ADMINS", ""))
    },
    'vt': {
        "name": "/vt/",
        "category": "thematic",
        "description": {"ru": "Витьюберы", "en": "VTubers", "jp": "Vチューバー"},
        "color1": "#ff9ff3", "color2": "#54a0ff",
        "username": "@tgach_vt_bot", "token": parse_token(os.getenv("VT_BOT_TOKEN")), "admins": parse_admins(os.getenv("VT_ADMINS", ""))
    },
    'au': {
        "name": "/au/",
        "category": "thematic",
        "description": {"ru": "Авто", "en": "Auto", "jp": "自動車"},
        "color1": "#95a5a6", "color2": "#2c3e50",
        "username": "@tgach_au_bot", "token": parse_token(os.getenv("AU_BOT_TOKEN")), "admins": parse_admins(os.getenv("AU_ADMINS", ""))
    },
    'news': {
        "name": "/news/",
        "category": "thematic",
        "description": {"ru": "Новости", "en": "News", "jp": "ニュース"},
        "color1": "#3498db", "color2": "#ecf0f1",
        "username": "@tgach_news_bot", "token": parse_token(os.getenv("NEWS_BOT_TOKEN")), "admins": parse_admins(os.getenv("NEWS_ADMINS", ""))
    },
    'ai': {
        "name": "/ai/",
        "category": "thematic",
        "description": {"ru": "AI / Нейронки", "en": "AI", "jp": "AI"},
        "color1": "#00bcd4", "color2": "#1e2b38",
        "username": "@tgach_ai_bot", "token": parse_token(os.getenv("AI_BOT_TOKEN")), "admins": parse_admins(os.getenv("AI_ADMINS", ""))
    },

    # === СИСТЕМА (system) ===
    'int': {
        "name": "/int/",
        "category": "system",
        "description": {"ru": "International", "en": "International", "jp": "国際"},
        "color1": "#2980b9", "color2": "#7f8c8d",
        "username": "@tgach_chatbot", "token": parse_token(os.getenv("INT_BOT_TOKEN")), "admins": parse_admins(os.getenv("INT_ADMINS", ""))
    },
    'meta': {
        "name": "/meta/",
        "category": "system",
        "description": {"ru": "Работа борды", "en": "Meta", "jp": "運営"},
        "color1": "#1abc9c", "color2": "#2c3e50",
        "username": "@tgach_meta_bot", "token": parse_token(os.getenv("META_BOT_TOKEN")), "admins": parse_admins(os.getenv("META_ADMINS", ""))
    },
    'thread': {
        "name": "/thread/",
        "category": "system",
        "description": {"ru": "Техраздел", "en": "Tech Support", "jp": "技術"},
        "color1": "#7f8c8d", "color2": "#bdc3c7",
        "username": "@thread_chatbot", "token": parse_token(os.getenv("THREAD_BOT_TOKEN")), "admins": parse_admins(os.getenv("THREAD_ADMINS", ""))
    },
    'test': {
        "name": "/test/",
        "category": "system",
        "description": {"ru": "Тест", "en": "Test", "jp": "テスト"},
        "color1": "#f39c12", "color2": "#34495e",
        "username": "@tgach_testbot", "token": parse_token(os.getenv("TEST_BOT_TOKEN")), "admins": parse_admins(os.getenv("TEST_ADMINS", ""))
    }
}
