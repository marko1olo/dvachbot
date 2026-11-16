# -*- coding: utf-8 -*-
"""
criminal_syndicate_engine.py — Modular Criminal PvP, Stealth & Darknet Syndicate for ТГАЧ / Двач
=================================================================================================
Architecture & Mechanics:
1. Criminal Profiles & State Management:
   - Wanted Stars (0 to 5★), Bounty Pool (₪), Dirty Balance (₪), Lockpicks count,
     Fake Ksiva credentials, 5G-Jammer stealth aura, [Крыса] debuff timer.
2. Command /scout (/шмон, /разведка):
   - Costs 150 ₪.
   - Blocks on target 5G-Jammer ("📡 СИГНАЛ ЗАГЛУШЕН!").
   - 75% success: Discloses target wealth bracket, equipped wardrobe armor, and traps (pepperspray, mirror).
   - 25% fail: Target spots thief with authentic 2ch rage alert, sets 15 min scout cooldown on target.
3. Command /pickpocket (/карманник, /щипач):
   - Requires & consumes 1 lockpick.
   - Enforces victim beginner protection (< 15 posts) & self-isolation (is_isolated == 1).
   - Steals 4%..10% of victim wallet (capped at 25,000 ₪) -> credited to thief's dirty_balance.
   - Increases thief wanted status (+1★ and +5,000 ₪ bounty).
   - Dynamic success rate: 65% base, amplified if victim sanity is low (< 50).
   - Success is 100% SILENT in chat, delivers secret DM confirmation to thief.
   - Fail is LOUD in public chat: [Крыса] status for 2 hours + 2,000 ₪ penalty paid to victim.
4. Command /arrest (/принять, /задержать):
   - Only authorized for badge_druzhinnik, ksiva_polkovnik, or fake_ksiva.
   - Targets wanted criminals (wanted_stars >= 1).
   - Fake Ksiva risk: 35% chance backfire (10,000 ₪ fine burned to Abu Yacht Fund, 30 min mute).
   - Legit arrest: Mutes criminal for stars * 15 minutes (max 75m).
   - Bounty split: 60% to arresting officer, 40% burned to Abu Yacht Fund.
   - Confiscates criminal's заточки and lockpicks. Resets wanted status to 0★ / 0 ₪.
5. Darknet Syndicate Catalog (/darknet, /даркнет, /buy_darknet):
   - lockpick (400 ₪), fake_ksiva (250 ₪), jammer (1,200 ₪, 1h).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
import random
import re
import difflib
import time
from typing import Any, Dict, List, Optional, Tuple

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.criminal_phrases import (
    ARREST_DRUZHINA_PHRASES,
    PICKPOCKET_LOUD_FAIL_PHRASES,
    PICKPOCKET_SILENT_SUCCESS_PHRASES,
    SCOUT_FAIL_SPOTTED_PHRASES,
    SCOUT_SUCCESS_COMMENTARY,
)

logger = logging.getLogger("runtime")

# Router instance
criminal_router = Router(name="criminal_router")
router = criminal_router

# -----------------------------------------------------------------------------
# Configuration Constants
# -----------------------------------------------------------------------------
SCOUT_COST = 150.0
SCOUT_COOLDOWN_SEC = 900.0  # 15 minutes on spotted fail
PICKPOCKET_MIN_PCT = 0.04
PICKPOCKET_MAX_PCT = 0.10
PICKPOCKET_MAX_CAP = 25000.0
PICKPOCKET_BASE_SUCCESS = 0.65
PICKPOCKET_FAIL_PENALTY = 2000.0
RAT_STATUS_DURATION_SEC = 7200.0  # 2 hours
BOUNTY_PER_STAR = 5000.0
WANTED_STAR_DECAY_SECONDS = 1800  # 30 минут на 1 звезду розыска (авто-снижение)
FAKE_KSIVA_BACKFIRE_CHANCE = 0.35
FAKE_KSIVA_FINE = 10000.0
FAKE_KSIVA_MUTE_SEC = 1800  # 30 minutes
MAX_WANTED_STARS = 5
MAX_ARREST_MUTE_MINUTES = 75
BOUNTY_OFFICER_SHARE = 0.60
BOUNTY_ABU_SHARE = 0.40

# In-memory scout cooldown registry: (thief_id, target_id) -> timestamp
scout_cooldowns: Dict[Tuple[int, int], float] = {}

# Darknet Catalog definition
DARKNET_CATALOG: Dict[str, Dict[str, Any]] = {
    "lockpick": {
        "id": "lockpick",
        "name": "🗝️ Отмычка",
        "price": 400.0,
        "desc": "Инструмент вора-карманника. Нужен для среза кошельков (/pickpocket). Расходуется при попытке.",
    },
    "fake_ksiva": {
        "id": "fake_ksiva",
        "name": "🪪 Палёная ксива",
        "price": 250.0,
        "desc": "Кустарное удостоверение майора из перехода. Позволяет вязать преступников (/arrest), но 35% шанс спалиться перед законом.",
    },
    "jammer": {
        "id": "jammer",
        "name": "📡 5G-глушилка",
        "price": 1200.0,
        "duration": 3600.0,
        "desc": "Подавитель слежки и радиосигналов. Полностью блокирует разведку твоих карманов (/scout) на 1 час.",
    },
    "master_key": {
        "id": "master_key",
        "name": "🗝️ Монтировка",
        "price": 5000.0,
        "desc": "Медвежатницкая монтировка — дает +20% к успеху взломов и обходу замков при карманных кражах (/pickpocket).",
    },
    "bribe_envelope": {
        "id": "bribe_envelope",
        "name": "✉️ Взятка следаку",
        "price": 2500.0,
        "desc": "Конверт следователю — мгновенно сбрасывает 1 звезду розыска без отсидки (/bribe_cop).",
    },
    "chloroform": {
        "id": "chloroform",
        "name": "🧪 Хлороформ",
        "price": 1500.0,
        "duration": 1800.0,
        "desc": "Хлороформ — усыпляет жертву на 30 мин, отключая перцовый баллончик (/chloroform).",
    },
    "fake_passport": {
        "id": "fake_passport",
        "name": "🪪 Поддельный паспорт",
        "price": 3500.0,
        "desc": "Новые документы и смена личности — мгновенно аннулирует статус федерального розыска полиции (0★) и размораживает счета (/fake_passport).",
    },
    "lawyer": {
        "id": "lawyer",
        "name": "⚖️ Адвокат",
        "price": 3000.0,
        "desc": "Услуги подпольного адвоката — подаёт апелляцию в прокуратуру, сбрасывает до 3★ розыска и аннулирует арест КПЗ (/lawyer).",
    },
}

# Alias mapping for backward compatibility and alternative dictionary imports
DARKNET_ITEMS: Dict[str, Dict[str, Any]] = DARKNET_CATALOG

# Dynamic wealth surcharge configuration for Darknet items
DARKNET_CONFIG: Dict[str, Dict[str, Any]] = {
    "lockpick": {"base": 400, "rate": 0.002, "max": 10000},
    "fake_ksiva": {"base": 250, "rate": 0.003, "max": 7500},
    "jammer": {"base": 1200, "rate": 0.005, "max": 35000},
    "master_key": {"base": 5000, "rate": 0.01, "max": 100000},
    "bribe_envelope": {"base": 2500, "rate": 0.008, "max": 75000},
    "chloroform": {"base": 1500, "rate": 0.004, "max": 25000},
    "fake_passport": {"base": 3500, "rate": 0.007, "max": 85000},
    "lawyer": {"base": 3000, "rate": 0.006, "max": 80000},
}

# Comprehensive multilingual alias mapping (Russian, English, Translit, Typos, Japanese)
DARKNET_ITEM_ALIASES: Dict[str, str] = {
    # lockpick (Отмычка) — Russian forms, English, Translit, Typos
    "lockpick": "lockpick",
    "lockpicks": "lockpick",
    "pick": "lockpick",
    "picks": "lockpick",
    "picklock": "lockpick",
    "picklocks": "lockpick",
    "lock_pick": "lockpick",
    "lock-pick": "lockpick",
    "lock pick": "lockpick",
    "отмычка": "lockpick",
    "отмычку": "lockpick",
    "отмычки": "lockpick",
    "отмычек": "lockpick",
    "отмычкой": "lockpick",
    "отмычкам": "lockpick",
    "отмычками": "lockpick",
    "отмычках": "lockpick",
    "отмычки_вора": "lockpick",
    "отмычка_вора": "lockpick",
    "отмычки вора": "lockpick",
    "отмычка вора": "lockpick",
    "воровская_отмычка": "lockpick",
    "воровская отмычка": "lockpick",
    "воровские_отмычки": "lockpick",
    "воровские отмычки": "lockpick",
    "отмычка для замков": "lockpick",
    "отмычка_для_замков": "lockpick",
    "отмычка-для-замков": "lockpick",
    "пикинг": "lockpick",
    "пик": "lockpick",
    "otmychka": "lockpick",
    "otmychki": "lockpick",
    "otmychku": "lockpick",
    "otmichka": "lockpick",
    "otmichki": "lockpick",
    "атмычка": "lockpick",
    "отмычька": "lockpick",
    "отмыка": "lockpick",
    "ピッキングツール": "lockpick",
    "ピッキング": "lockpick",

    # fake_ksiva (Палёная ксива) — Russian forms, English, Translit, Typos
    "fake_ksiva": "fake_ksiva",
    "fake_id": "fake_ksiva",
    "fake_badge": "fake_ksiva",
    "fakeksiva": "fake_ksiva",
    "fake": "fake_ksiva",
    "ksiva": "fake_ksiva",
    "ksivy": "fake_ksiva",
    "ksivu": "fake_ksiva",
    "fake_pass": "fake_ksiva",
    "counterfeit_id": "fake_ksiva",
    "ксива": "fake_ksiva",
    "ксиву": "fake_ksiva",
    "ксивы": "fake_ksiva",
    "ксивой": "fake_ksiva",
    "ксивам": "fake_ksiva",
    "паленая_ксива": "fake_ksiva",
    "палёная_ксива": "fake_ksiva",
    "паленая ксива": "fake_ksiva",
    "палёная ксива": "fake_ksiva",
    "паленая-ксива": "fake_ksiva",
    "палёная-ксива": "fake_ksiva",
    "паленка": "fake_ksiva",
    "палёнка": "fake_ksiva",
    "паленку": "fake_ksiva",
    "палёнку": "fake_ksiva",
    "паленая": "fake_ksiva",
    "палёная": "fake_ksiva",
    "паленую": "fake_ksiva",
    "палёную": "fake_ksiva",
    "удостоверение": "fake_ksiva",
    "удостоверение_майора": "fake_ksiva",
    "удостоверение майора": "fake_ksiva",
    "корочка": "fake_ksiva",
    "корочку": "fake_ksiva",
    "корочки": "fake_ksiva",
    "корка": "fake_ksiva",
    "корку": "fake_ksiva",
    "фальшивка": "fake_ksiva",
    "фальшивку": "fake_ksiva",
    "фальшивое_удостоверение": "fake_ksiva",
    "фальшивое удостоверение": "fake_ksiva",
    "липовая_ксива": "fake_ksiva",
    "липовая ксива": "fake_ksiva",
    "липовая-ксива": "fake_ksiva",
    "липа": "fake_ksiva",
    "липу": "fake_ksiva",
    "fake ksiva": "fake_ksiva",
    "fake-ksiva": "fake_ksiva",
    "fake id": "fake_ksiva",
    "fake-id": "fake_ksiva",
    "fake badge": "fake_ksiva",
    "fake-badge": "fake_ksiva",
    "palenaya_ksiva": "fake_ksiva",
    "palenaya ksiva": "fake_ksiva",
    "korochka": "fake_ksiva",
    "ксыва": "fake_ksiva",
    "ксыву": "fake_ksiva",
    "фальшывка": "fake_ksiva",
    "偽造警察手帳": "fake_ksiva",
    "偽造手帳": "fake_ksiva",

    # jammer (5G-глушилка) — Russian forms, English, Translit, Typos
    "jammer": "jammer",
    "jammers": "jammer",
    "5g_jammer": "jammer",
    "5g-jammer": "jammer",
    "5g jammer": "jammer",
    "5g": "jammer",
    "5г": "jammer",
    "signal_jammer": "jammer",
    "signal jammer": "jammer",
    "scrambler": "jammer",
    "глушилка": "jammer",
    "глушилку": "jammer",
    "глушилки": "jammer",
    "глушилкой": "jammer",
    "глушитель": "jammer",
    "глушителя": "jammer",
    "радиоглушилка": "jammer",
    "5g_глушилка": "jammer",
    "5g-глушилка": "jammer",
    "5g глушилка": "jammer",
    "5г_глушилка": "jammer",
    "5г-глушилка": "jammer",
    "5г глушилка": "jammer",
    "джаммер": "jammer",
    "джаммера": "jammer",
    "джамер": "jammer",
    "подавитель": "jammer",
    "подавитель_сигнала": "jammer",
    "подавитель сигнала": "jammer",
    "подавитель-сигнала": "jammer",
    "подавитель_слежки": "jammer",
    "подавитель слежки": "jammer",
    "glushilka": "jammer",
    "glushilku": "jammer",
    "glushitel": "jammer",
    "dzhamer": "jammer",
    "dzhammer": "jammer",
    "глушылка": "jammer",
    "глушылку": "jammer",
    "5г глушылка": "jammer",
    "5g 電波ジャマー": "jammer",
    "電波ジャマー": "jammer",
    "ジャマー": "jammer",

    # master_key (Монтировка / Мастер-ключ) — Russian forms, English, Translit, Typos
    "master_key": "master_key",
    "masterkey": "master_key",
    "master_keys": "master_key",
    "master key": "master_key",
    "master-key": "master_key",
    "crowbar": "master_key",
    "crowbars": "master_key",
    "prybar": "master_key",
    "burglar_tool": "master_key",
    "key": "master_key",
    "монтировка": "master_key",
    "монтировку": "master_key",
    "монтировки": "master_key",
    "монтировкой": "master_key",
    "мастер_ключ": "master_key",
    "мастер-ключ": "master_key",
    "мастер ключ": "master_key",
    "мастерключ": "master_key",
    "фомка": "master_key",
    "фомку": "master_key",
    "фомки": "master_key",
    "фомкой": "master_key",
    "фомка_медвежатника": "master_key",
    "фомка медвежатника": "master_key",
    "фомка-медвежатника": "master_key",
    "медвежатник": "master_key",
    "багор": "master_key",
    "баул": "master_key",
    "montirovka": "master_key",
    "montirovku": "master_key",
    "fomka": "master_key",
    "fomku": "master_key",
    "мантировка": "master_key",
    "мантировку": "master_key",
    "монтировк": "master_key",
    "マスターキー": "master_key",
    "バール": "master_key",

    # bribe_envelope (Конверт со взяткой) — Russian forms, English, Translit, Typos
    "bribe_envelope": "bribe_envelope",
    "bribe_envelopes": "bribe_envelope",
    "bribeenvelope": "bribe_envelope",
    "bribe envelope": "bribe_envelope",
    "bribe-envelope": "bribe_envelope",
    "envelope": "bribe_envelope",
    "envelopes": "bribe_envelope",
    "bribe": "bribe_envelope",
    "bribes": "bribe_envelope",
    "cop_bribe": "bribe_envelope",
    "cop bribe": "bribe_envelope",
    "cop-bribe": "bribe_envelope",
    "bribe_cop": "bribe_envelope",
    "bribecop": "bribe_envelope",
    "bribe cop": "bribe_envelope",
    "bribe-cop": "bribe_envelope",
    "detective_bribe": "bribe_envelope",
    "detective bribe": "bribe_envelope",
    "payoff": "bribe_envelope",
    "взятка": "bribe_envelope",
    "взятку": "bribe_envelope",
    "взятки": "bribe_envelope",
    "взяткой": "bribe_envelope",
    "конверт": "bribe_envelope",
    "конверты": "bribe_envelope",
    "конвертик": "bribe_envelope",
    "конверта": "bribe_envelope",
    "конвертом": "bribe_envelope",
    "конверт_со_взяткой": "bribe_envelope",
    "конверт со взяткой": "bribe_envelope",
    "конверт-со-взяткой": "bribe_envelope",
    "конверт_с_взяткой": "bribe_envelope",
    "конверт с взяткой": "bribe_envelope",
    "конверт-с-взяткой": "bribe_envelope",
    "конверт_для_взятки": "bribe_envelope",
    "конверт для взятки": "bribe_envelope",
    "взятка_следователю": "bribe_envelope",
    "взятка следователю": "bribe_envelope",
    "взятка-следователю": "bribe_envelope",
    "взятка_следаку": "bribe_envelope",
    "взятка следаку": "bribe_envelope",
    "взятка-следаку": "bribe_envelope",
    "взятка_копу": "bribe_envelope",
    "взятка копу": "bribe_envelope",
    "взятка-копу": "bribe_envelope",
    "подкуп_копа": "bribe_envelope",
    "подкуп копа": "bribe_envelope",
    "подкуп-копа": "bribe_envelope",
    "подкуп_следователя": "bribe_envelope",
    "подкуп следователя": "bribe_envelope",
    "подкуп": "bribe_envelope",
    "откуп": "bribe_envelope",
    "откупиться": "bribe_envelope",
    "следак": "bribe_envelope",
    "следователь": "bribe_envelope",
    "konvert": "bribe_envelope",
    "konvert_so_vzyatkoy": "bribe_envelope",
    "konvert so vzyatkoy": "bribe_envelope",
    "vzyatka": "bribe_envelope",
    "vzjatka": "bribe_envelope",
    "otkup": "bribe_envelope",
    "podkup": "bribe_envelope",
    "канверт": "bribe_envelope",
    "канверт со взяткой": "bribe_envelope",
    "взятка следоку": "bribe_envelope",
    "взятка следавателю": "bribe_envelope",
    "賄賂の封筒": "bribe_envelope",
    "賄賂": "bribe_envelope",

    # chloroform (Хлороформ) — Russian forms, English, Translit, Typos
    "chloroform": "chloroform",
    "chloroforms": "chloroform",
    "chlor": "chloroform",
    "chloroforme": "chloroform",
    "sleep_potion": "chloroform",
    "sleeping_potion": "chloroform",
    "knockout": "chloroform",
    "хлороформ": "chloroform",
    "хлороформа": "chloroform",
    "хлороформу": "chloroform",
    "хлороформом": "chloroform",
    "хлороформе": "chloroform",
    "хлорик": "chloroform",
    "хлорика": "chloroform",
    "усыпитель": "chloroform",
    "усыпителя": "chloroform",
    "снотворное": "chloroform",
    "снотворного": "chloroform",
    "флакон_хлороформа": "chloroform",
    "флакон хлороформа": "chloroform",
    "флакон-хлороформа": "chloroform",
    "флакон": "chloroform",
    "пузырек_хлороформа": "chloroform",
    "пузырек хлороформа": "chloroform",
    "хлороформ_флакон": "chloroform",
    "хлороформ флакон": "chloroform",
    "hloroform": "chloroform",
    "khloroform": "chloroform",
    "hlorik": "chloroform",
    "usypitel": "chloroform",
    "хлораформ": "chloroform",
    "хлороформь": "chloroform",
    "хлароформ": "chloroform",
    "クロロホルム": "chloroform",

    # fake_passport (Поддельный паспорт) — Russian forms, English, Translit, Typos
    "fake_passport": "fake_passport",
    "документы": "fake_passport",
    "документ": "fake_passport",
    "пасспорт": "fake_passport",
    "доки": "fake_passport",
    "fakepassport": "fake_passport",
    "fake-passport": "fake_passport",
    "fake passport": "fake_passport",
    "fake_pass": "fake_passport",
    "fakepass": "fake_passport",
    "passport": "fake_passport",
    "passports": "fake_passport",
    "pass": "fake_passport",
    "паспорт": "fake_passport",
    "паспорта": "fake_passport",
    "паспорту": "fake_passport",
    "паспортом": "fake_passport",
    "паспорте": "fake_passport",
    "паспорты": "fake_passport",
    "поддельный_паспорт": "fake_passport",
    "поддельный паспорт": "fake_passport",
    "поддельный-паспорт": "fake_passport",
    "поддельного_паспорта": "fake_passport",
    "поддельного паспорта": "fake_passport",
    "поддельному_паспорту": "fake_passport",
    "поддельным_паспортом": "fake_passport",
    "липовый_паспорт": "fake_passport",
    "липовый паспорт": "fake_passport",
    "липовый-паспорт": "fake_passport",
    "липового_паспорта": "fake_passport",
    "фальшивый_паспорт": "fake_passport",
    "фальшивый паспорт": "fake_passport",
    "фальшивый-паспорт": "fake_passport",
    "смена_паспорта": "fake_passport",
    "смена паспорта": "fake_passport",
    "смена-паспорта": "fake_passport",
    "новый_паспорт": "fake_passport",
    "новый паспорт": "fake_passport",
    "новый-паспорт": "fake_passport",
    "переоформление": "fake_passport",
    "переоформление паспорта": "fake_passport",
    "смена личности": "fake_passport",
    "смена_личности": "fake_passport",
    "паспортные данные": "fake_passport",
    "fake_id_passport": "fake_passport",
    "clean_record": "fake_passport",

    # lawyer (Адвокат) — Russian forms, English, Translit, Typos
    "lawyer": "lawyer",
    "lawyers": "lawyer",
    "advokat": "lawyer",
    "advocate": "lawyer",
    "advocates": "lawyer",
    "attorney": "lawyer",
    "attorneys": "lawyer",
    "barrister": "lawyer",
    "defense": "lawyer",
    "defense_attorney": "lawyer",
    "defense lawyer": "lawyer",
    "адвокат": "lawyer",
    "адвокаты": "lawyer",
    "адвоката": "lawyer",
    "адвокату": "lawyer",
    "адвокатом": "lawyer",
    "адвокате": "lawyer",
    "адвокатов": "lawyer",
    "адвокатам": "lawyer",
    "юрист": "lawyer",
    "юристы": "lawyer",
    "юриста": "lawyer",
    "юристу": "lawyer",
    "юристом": "lawyer",
    "юристе": "lawyer",
    "защитник": "lawyer",
    "защитники": "lawyer",
    "защитника": "lawyer",
    "защитнику": "lawyer",
    "защитником": "lawyer",
    "правозащитник": "lawyer",
    "стряпчий": "lawyer",
}


def resolve_darknet_item_id(query: Optional[str]) -> Optional[str]:
    """
    Resolves any item ID, English synonym, Russian alias, translit, typo,
    Japanese term, or multi-word phrase to the canonical Darknet item key.
    Includes full fuzzy difflib fallback with 100% precision.
    """
    if not query:
        return None
    raw = query.strip().lower()
    if not raw:
        return None

    # 1. Direct match in catalog
    if raw in DARKNET_CATALOG:
        return raw

    # 2. Direct match in aliases
    if raw in DARKNET_ITEM_ALIASES:
        return DARKNET_ITEM_ALIASES[raw]

    # 3. Clean punctuation and normalize spacing / hyphens
    norm_underscore = re.sub(r"[\s\-]+", "_", raw).strip("_")
    if norm_underscore in DARKNET_CATALOG:
        return norm_underscore
    if norm_underscore in DARKNET_ITEM_ALIASES:
        return DARKNET_ITEM_ALIASES[norm_underscore]

    norm_space = re.sub(r"[_\\-]+", " ", raw).strip()
    if norm_space in DARKNET_ITEM_ALIASES:
        return DARKNET_ITEM_ALIASES[norm_space]

    norm_clean = re.sub(r"[^\w\s]", "", raw).strip()
    if norm_clean in DARKNET_ITEM_ALIASES:
        return DARKNET_ITEM_ALIASES[norm_clean]

    # 4. Multi-token fallback: check first token or multi-token pairs
    tokens = raw.split()
    if len(tokens) > 1:
        first_token = tokens[0]
        if first_token in DARKNET_CATALOG:
            return first_token
        if first_token in DARKNET_ITEM_ALIASES:
            return DARKNET_ITEM_ALIASES[first_token]
        pair_space = " ".join(tokens[:2])
        if pair_space in DARKNET_ITEM_ALIASES:
            return DARKNET_ITEM_ALIASES[pair_space]
        pair_under = "_".join(tokens[:2])
        if pair_under in DARKNET_ITEM_ALIASES:
            return DARKNET_ITEM_ALIASES[pair_under]

    # 5. Fuzzy match against all known aliases and catalog keys
    keys_pool = list(DARKNET_CATALOG.keys()) + list(DARKNET_ITEM_ALIASES.keys())
    matches = difflib.get_close_matches(raw, keys_pool, n=1, cutoff=0.70)
    if not matches and norm_clean != raw:
        matches = difflib.get_close_matches(norm_clean, keys_pool, n=1, cutoff=0.70)
    if matches:
        matched = matches[0]
        if matched in DARKNET_CATALOG:
            return matched
        if matched in DARKNET_ITEM_ALIASES:
            return DARKNET_ITEM_ALIASES[matched]

    # 6. Check individual tokens with fuzzy matching
    for tok in tokens:
        clean_tok = re.sub(r"[^\w]", "", tok).strip()
        if len(clean_tok) < 3:
            continue
        if clean_tok in DARKNET_CATALOG:
            return clean_tok
        if clean_tok in DARKNET_ITEM_ALIASES:
            return DARKNET_ITEM_ALIASES[clean_tok]
        tok_matches = difflib.get_close_matches(clean_tok, keys_pool, n=1, cutoff=0.75)
        if tok_matches:
            matched = tok_matches[0]
            if matched in DARKNET_CATALOG:
                return matched
            if matched in DARKNET_ITEM_ALIASES:
                return DARKNET_ITEM_ALIASES[matched]

    return None

def get_darknet_item_price(item_key: str, balance: float) -> int:
    """
    Calculates the dynamic price of a darknet item scaled to user's wealth.
    Novices (balance <= 10,000 ₪) pay pure base price.
    Wealthy users (balance > 10,000 ₪) pay base + surcharge up to configured cap.
    Supports item aliases (Russian, English synonyms).
    """
    cid = resolve_darknet_item_id(item_key) or (item_key or "").strip().lower()
    cfg = DARKNET_CONFIG.get(cid)
    if not cfg:
        cat_item = DARKNET_CATALOG.get(cid)
        return int(cat_item["price"]) if cat_item else 0

    base = cfg["base"]
    try:
        bal = float(balance or 0.0)
    except (ValueError, TypeError):
        bal = 0.0

    if not math.isfinite(bal) or bal <= 10000.0:
        return base

    surcharge = int(bal * cfg["rate"])
    return min(cfg["max"], base + surcharge)


def calculate_scout_cost(caller_balance: float) -> float:
    """
    Dynamic wealth scaling for /scout:
    max(150.0, min(15000.0, 150.0 + float(int(caller_balance * 0.003))))
    Novices pay 150 ₪; oligarchs with 5M pay 15,000 ₪!
    """
    try:
        bal = float(caller_balance or 0.0)
    except (ValueError, TypeError):
        bal = 0.0
    if not math.isfinite(bal) or bal <= 0:
        return 150.0
    return float(max(150.0, min(15000.0, 150.0 + float(int(bal * 0.003)))))

# -----------------------------------------------------------------------------
# State and Schema Management Helpers
# -----------------------------------------------------------------------------

def get_criminal_profile(active_items: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extracts and sanitizes the criminal record and syndicate inventory from active_items.
    Safely handles None, corrupted values, and type discrepancies.
    """
    if not isinstance(active_items, dict):
        active_items = {}

    try:
        raw_stars = int(active_items.get("wanted_stars", 0) or 0)
    except (ValueError, TypeError):
        raw_stars = 0
    wanted_stars = max(0, min(MAX_WANTED_STARS, raw_stars))

    try:
        raw_bounty = float(active_items.get("bounty_pool") or active_items.get("bounty") or 0.0)
    except (ValueError, TypeError):
        raw_bounty = 0.0
    bounty_pool = max(0.0, round(raw_bounty, 2))

    try:
        raw_dirty = float(active_items.get("dirty_balance", 0.0) or 0.0)
    except (ValueError, TypeError):
        raw_dirty = 0.0
    dirty_balance = max(0.0, round(raw_dirty, 2))

    try:
        raw_lockpicks = int(active_items.get("lockpick", 0) or 0)
    except (ValueError, TypeError):
        raw_lockpicks = 0
    lockpick = max(0, raw_lockpicks)

    raw_fake = active_items.get("fake_ksiva", 0)
    if isinstance(raw_fake, bool):
        fake_ksiva = 1 if raw_fake else 0
    else:
        try:
            fake_ksiva = max(0, int(raw_fake or 0))
        except (ValueError, TypeError):
            fake_ksiva = 0

    try:
        jammer_until = float(active_items.get("jammer_until", 0.0) or 0.0)
    except (ValueError, TypeError):
        jammer_until = 0.0

    try:
        rat_until = float(active_items.get("rat_until", 0.0) or 0.0)
    except (ValueError, TypeError):
        rat_until = 0.0

    try:
        raw_mkey = int(active_items.get("master_key", 0) or 0)
    except (ValueError, TypeError):
        raw_mkey = 0
    master_key = max(0, raw_mkey)

    try:
        raw_bribe = int(active_items.get("bribe_envelope", 0) or 0)
    except (ValueError, TypeError):
        raw_bribe = 0
    bribe_envelope = max(0, raw_bribe)

    try:
        raw_chlor = int(active_items.get("chloroform", 0) or 0)
    except (ValueError, TypeError):
        raw_chlor = 0
    chloroform = max(0, raw_chlor)

    try:
        raw_pass = int(active_items.get("fake_passport", 0) or 0)
    except (ValueError, TypeError):
        raw_pass = 0
    fake_passport = max(0, raw_pass)

    try:
        raw_lawyer = int(active_items.get("lawyer", 0) or 0)
    except (ValueError, TypeError):
        raw_lawyer = 0
    lawyer = max(0, raw_lawyer)

    try:
        chloroformed_until = float(active_items.get("chloroformed_until", 0.0) or 0.0)
    except (ValueError, TypeError):
        chloroformed_until = 0.0

    now = time.time()
    # Применяем таймер автоматического снижения звезд розыска (anti-softlock)
    try:
        if wanted_stars > 0:
            apply_wanted_decay(active_items, current_ts=now)
            wanted_stars = int(active_items.get("wanted_stars", 0) or 0)
            bounty_pool = float(active_items.get("bounty_pool", 0.0) or 0.0)
    except Exception:
        pass

    return {
        "wanted_stars": wanted_stars,
        "bounty_pool": bounty_pool,
        "dirty_balance": dirty_balance,
        "lockpick": lockpick,
        "fake_ksiva": fake_ksiva,
        "master_key": master_key,
        "bribe_envelope": bribe_envelope,
        "chloroform": chloroform,
        "fake_passport": fake_passport,
        "lawyer": lawyer,
        "jammer_until": jammer_until,
        "rat_until": rat_until,
        "chloroformed_until": chloroformed_until,
        "is_rat": rat_until > now,
        "is_jammed": jammer_until > now,
        "is_chloroformed": chloroformed_until > now,
    }


def add_dirty_shekels(active_items: Dict[str, Any], amount: float) -> float:
    """
    Credits stolen marked/dirty shekels to user's syndicate ledger.
    Returns the new dirty_balance.
    """
    if not isinstance(active_items, dict):
        return 0.0
    curr = float(active_items.get("dirty_balance", 0.0) or 0.0)
    new_bal = max(0.0, round(curr + float(amount), 2))
    active_items["dirty_balance"] = new_bal
    return new_bal


def add_wanted_stars(active_items: Dict[str, Any], stars: int, bounty: float) -> Tuple[int, float]:
    """
    Increments criminal wanted level (clamped 0..5) and accumulates bounty pool.
    Returns (new_stars, new_bounty).
    """
    if not isinstance(active_items, dict):
        return 0, 0.0
    curr_stars = int(active_items.get("wanted_stars", 0) or 0)
    new_stars = max(0, min(MAX_WANTED_STARS, curr_stars + int(stars)))

    curr_bounty = float(active_items.get("bounty_pool") or active_items.get("bounty") or 0.0)
    new_bounty = max(0.0, round(curr_bounty + float(bounty), 2))

    active_items["wanted_stars"] = new_stars
    active_items["bounty_pool"] = new_bounty
    active_items["bounty"] = new_bounty
    active_items["wanted_updated_at"] = time.time()
    return new_stars, new_bounty

def apply_wanted_decay(active_items: Dict[str, Any], current_ts: Optional[float] = None) -> bool:
    """
    Автоматически снижает уровень розыска со временем (1 звезда каждые 30 минут).
    Предотвращает перманентный софтлок игроков в розыске при отсутствии средств или в офлайне.
    Возвращает True, если статус розыска изменился.
    """
    if not isinstance(active_items, dict):
        return False
    stars = int(active_items.get("wanted_stars", 0) or 0)
    if stars <= 0:
        return False

    now = float(current_ts) if current_ts is not None else time.time()
    updated_at = float(active_items.get("wanted_updated_at", 0.0) or 0.0)
    if updated_at <= 0:
        active_items["wanted_updated_at"] = now
        return False

    elapsed = now - updated_at
    if elapsed < WANTED_STAR_DECAY_SECONDS:
        return False

    decay_stars = int(elapsed // WANTED_STAR_DECAY_SECONDS)
    if decay_stars <= 0:
        return False

    new_stars = max(0, stars - decay_stars)
    curr_bounty = float(active_items.get("bounty_pool") or active_items.get("bounty") or 0.0)
    new_bounty = max(0.0, round(curr_bounty * (new_stars / stars), 2)) if stars > 0 and new_stars > 0 else 0.0

    active_items["wanted_stars"] = new_stars
    active_items["bounty_pool"] = new_bounty
    active_items["bounty"] = new_bounty
    active_items["wanted_updated_at"] = now - (elapsed % WANTED_STAR_DECAY_SECONDS)
    return True


async def check_and_release_sentence_served(
    db: Any,
    user_id: int,
    board_id: str,
    active_items: Optional[Dict[str, Any]] = None,
    current_ts: Optional[float] = None
) -> bool:
    """
    Проверяет отбытие срока ареста (КПЗ / мута). Если таймер отсидки истёк,
    полностью снимает розыск и размораживает банковские счета.
    """
    now = float(current_ts) if current_ts is not None else time.time()
    try:
        async with db.execute(
            "SELECT expires_at FROM Mutes WHERE user_id = ? AND (mute_type = 'arrest' OR reason LIKE '%арест%' OR reason LIKE '%Арест%') ORDER BY expires_at DESC LIMIT 1",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            exp = float(row[0])
            if now >= exp:
                await db.execute(
                    "DELETE FROM Mutes WHERE user_id = ? AND (mute_type = 'arrest' OR reason LIKE '%арест%' OR reason LIKE '%Арест%') AND expires_at <= ?",
                    (user_id, now)
                )
                if hasattr(db, "commit"):
                    await db.commit()
                items = active_items if active_items is not None else await load_user_active_items(db, user_id, board_id)
                clear_wanted_status(items)
                await sync_user_criminal_status(db, user_id, items)
                await save_user_active_items(db, user_id, board_id, items)
                return True
    except Exception as e:
        logger.warning(f"Error checking sentence served for {user_id}: {e}")
    return False



def clear_wanted_status(active_items: Dict[str, Any]) -> float:
    """
    Resets wanted stars and bounty pool to zero (post-arrest or syndicate pardon).
    Returns the cleared bounty pool amount.
    """
    if not isinstance(active_items, dict):
        return 0.0
    cleared = float(active_items.get("bounty_pool") or active_items.get("bounty") or 0.0)
    active_items["wanted_stars"] = 0
    active_items["bounty_pool"] = 0.0
    active_items["bounty"] = 0.0
    active_items["wanted_updated_at"] = time.time()
    return max(0.0, round(cleared, 2))


# -----------------------------------------------------------------------------
# Database Synchronization Helpers
# -----------------------------------------------------------------------------

async def sync_user_criminal_status(db: Any, user_id: int, active_items: Dict[str, Any]) -> None:
    """
    Synchronizes criminal syndicate status (wanted_stars, bounty_pool, dirty_balance, bribe_envelope)
    across ALL board records in the Users table for this user.
    """
    stars = int(active_items.get("wanted_stars", 0) or 0)
    bounty = float(active_items.get("bounty_pool", 0.0) or active_items.get("bounty", 0.0) or 0.0)
    dirty = float(active_items.get("dirty_balance", 0.0) or 0.0)
    envelopes = int(active_items.get("bribe_envelope", 0) or 0)
    shop_bribes = int(active_items.get("bribe", 0) or 0)
    fake_pass = int(active_items.get("fake_passport", 0) or 0)
    lawyer_cnt = int(active_items.get("lawyer", 0) or 0)
    wanted_up = float(active_items.get("wanted_updated_at", 0.0) or 0.0)

    try:
        async with db.execute("SELECT board_id, active_items FROM Users WHERE user_id = ?", (user_id,)) as cur:
            user_rows = await cur.fetchall()

        if user_rows:
            for b_row_id, a_str in user_rows:
                b_data = json.loads(a_str) if a_str else {}
                b_data["wanted_stars"] = stars
                b_data["bounty_pool"] = bounty
                b_data["bounty"] = bounty
                b_data["dirty_balance"] = dirty
                b_data["bribe_envelope"] = envelopes
                b_data["bribe"] = shop_bribes
                b_data["fake_passport"] = fake_pass
                b_data["lawyer"] = lawyer_cnt
                if wanted_up > 0:
                    b_data["wanted_updated_at"] = wanted_up
                await db.execute(
                    "UPDATE Users SET active_items = ? WHERE user_id = ? AND board_id = ?",
                    (json.dumps(b_data, ensure_ascii=False), user_id, b_row_id),
                )
            if hasattr(db, "commit"):
                await db.commit()
    except Exception as e:
        logger.warning(f"[sync_user_criminal_status] Multi-board sync error for {user_id}: {e}")


async def load_user_active_items(db: Any, user_id: int, board_id: str) -> Dict[str, Any]:
    """
    Loads active_items dictionary from Users table for a given user and board,
    supporting cross-board fallback to preserve criminal syndicate status.
    """
    try:
        from common.bot_helpers import _get_user_active_items
        items = await _get_user_active_items(db, user_id, board_id)
        if isinstance(items, dict) and items:
            return items
    except Exception:
        pass

    try:
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? AND board_id = ?",
            (user_id, board_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    return data
    except Exception as e:
        logger.warning(f"[CRIMINAL] Failed to load active_items for user {user_id}: {e}")

    try:
        async with db.execute(
            "SELECT active_items FROM Users WHERE user_id = ? ORDER BY CASE WHEN board_id = 'b' THEN 0 ELSE 1 END LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    return data
    except Exception:
        pass

    return {}

async def save_user_active_items(db: Any, user_id: int, board_id_or_items: Any, items_or_board_id: Any = None) -> None:
    """
    Persists active_items dictionary into Users table atomically.
    Supports both (db, user_id, board_id, active_items) and (db, user_id, active_items, board_id="b").
    """
    if isinstance(board_id_or_items, dict) and (items_or_board_id is None or isinstance(items_or_board_id, str)):
        active_items = board_id_or_items
        board_id = items_or_board_id or "b"
    elif isinstance(board_id_or_items, str) and isinstance(items_or_board_id, dict):
        board_id = board_id_or_items
        active_items = items_or_board_id
    else:
        active_items = board_id_or_items if isinstance(board_id_or_items, dict) else (items_or_board_id if isinstance(items_or_board_id, dict) else {})
        board_id = str(board_id_or_items) if isinstance(board_id_or_items, str) else (str(items_or_board_id) if items_or_board_id else "b")

    serialized = json.dumps(active_items, ensure_ascii=False)
    try:
        await db.execute(
            "INSERT INTO Users (user_id, board_id, active_items) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, board_id) DO UPDATE SET active_items = excluded.active_items",
            (user_id, board_id, serialized),
        )
        if hasattr(db, "commit"):
            await db.commit()
    except Exception as e:
        logger.error(f"[CRIMINAL] Error persisting active_items for {user_id}: {e}")


def format_anon_id(user_id: int) -> str:
    """
    Returns authentic anon board ID tag.
    """
    try:
        from common.anon_identity import get_anon_id
        return get_anon_id(user_id)
    except Exception:
        return f"{user_id % 100000:05d}"

def get_target_wealth_bracket(balance: float) -> str:
    """
    Calculates 2ch wealth classification for scout reports.
    """
    if balance < 5000.0:
        return "Нищий сыч (до 5,000 ₪)"
    elif balance <= 50000.0:
        return "Работяга с завода (5,000 - 50,000 ₪)"
    elif balance <= 250000.0:
        return "Зажиточный мажор (50,000 - 250,000 ₪)"
    elif balance <= 1000000.0:
        return "Подпольный крипто-олигарх (250k - 1M ₪)"
    else:
        return "Жирный кит / Владелец борды (> 1,000,000 ₪)"

def detect_target_armor(target_items: Dict[str, Any]) -> str:
    """
    Inspects equipped clothing/armor from wardrobe catalog.
    """
    try:
        from wardrobe_engine import get_equipped_gear
        gear = get_equipped_gear(target_items)
        equipped_desc = []
        for slot, item in gear.items():
            if item and isinstance(item, dict):
                slot_name = slot.capitalize()
                item_name = item.get("name", item.get("id", "Снаряжение"))
                equipped_desc.append(f"{slot_name}: {item_name}")
        if equipped_desc:
            return ", ".join(equipped_desc)
    except Exception:
        pass

    # Direct fallback inspection
    direct_slots = []
    for slot in ("head", "body", "torso", "face", "feet"):
        val = target_items.get(f"equipped_{slot}")
        if val:
            direct_slots.append(f"{slot}: {val}")
    if direct_slots:
        return ", ".join(direct_slots)

    return "Голый сыч в растянутых трениках (без брони)"

def detect_target_traps(target_items: Dict[str, Any], now: Optional[float] = None) -> List[str]:
    """
    Detects active defensive traps: Pepperspray and Mirror/Reflect shield.
    If target is currently chloroformed (chloroformed_until > now), pepperspray is neutralized.
    """
    if now is None:
        now = time.time()
    traps = []
    is_chloroformed = float(target_items.get("chloroformed_until", 0.0) or 0.0) > now

    if target_items.get("pepperspray_gun") or target_items.get("pepperspray"):
        if is_chloroformed:
            traps.append("🧯 Перцовый баллончик «Шпага» (💤 нейтрализован хлороформом, не сработает)")
        else:
            traps.append("🧯 Перцовый баллончик «Шпага» (авто-струя в ебло грабителю)")

    if (float(target_items.get("reflect_shield_until", 0.0) or 0.0) > now) or target_items.get("shield"):
        traps.append("🪞 Зеркало заднего вида (полное отражение нападения)")
    return traps


def get_target_sanity_score(target_items: Dict[str, Any]) -> int:
    """
    Calculates target sanity score (0..100). Low sanity makes target vulnerable to pickpockets.
    """
    try:
        from wardrobe_engine import get_wardrobe_total_stats
        stats = get_wardrobe_total_stats(target_items)
        base = 100 + int(stats.get("total_sanity", 0) or 0)
        return max(0, min(100, base))
    except Exception:
        return 100


async def safe_resolve_target(message: types.Message, db: Any = None) -> Optional[int]:
    """
    Resolves target user_id from message reply, command text args (Anon-ID, TG ID), or mentions.
    """
    # 1. Reply resolution using robust common helper
    if message.reply_to_message:
        try:
            from common.bot_helpers import get_author_id_by_reply
            reply_target = await get_author_id_by_reply(message)
            if reply_target and reply_target > 0:
                return int(reply_target)
        except Exception:
            pass

        chat_id = message.reply_to_message.chat.id
        msg_id = message.reply_to_message.message_id

        # Shared state message to post fallback
        try:
            import shared_state
            async with shared_state.storage_lock:
                p_num = shared_state.message_to_post.get((chat_id, msg_id))
                if p_num and p_num in shared_state.messages_storage:
                    author_id = shared_state.messages_storage[p_num].get("author_id")
                    if author_id:
                        return int(author_id)
        except Exception:
            pass

        # Database post copy lookup fallback
        try:
            from common.database import get_post_info_by_copy
            info = await get_post_info_by_copy(chat_id, msg_id)
            if info and len(info) > 1 and info[1]:
                return int(info[1])
        except Exception:
            pass

        if message.reply_to_message.from_user:
            return int(message.reply_to_message.from_user.id)

    # 2. Argument-based resolution (e.g. /pickpocket [Локада6], /scout 12345678, /arrest [Анон4])
    raw_text = None
    try:
        raw_text = getattr(message, "text", None) or getattr(message, "caption", None)
    except Exception:
        pass
    text = raw_text or ""
    parts = text.strip().split()
    if len(parts) >= 2:
        candidate = parts[1].strip()
        if candidate:
            try:
                if db is None:
                    from common.db_pool import get_pool
                    db = await get_pool()
                from common.bot_helpers import resolve_target_user_id
                resolved = await resolve_target_user_id(db, candidate)
                if resolved and resolved > 0:
                    return int(resolved)
            except Exception:
                pass

    return None


# -----------------------------------------------------------------------------
# Core Mechanics: Scout (/scout, /шмон, /разведка)
# -----------------------------------------------------------------------------

async def execute_scout(
    db: Any,
    thief_id: int,
    target_id: int,
    board_id: str,
    roll: Optional[float] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes criminal scouting on target.
    - Costs 150 ₪.
    - Blocked if target has active jammer_until > now.
    - 75% success: discloses wealth bracket, equipped armor, traps.
    - 25% fail: target spots thief with salty 2ch alert, gives 15m cooldown.
    """
    now = time.time()
    thief_tag = format_anon_id(thief_id)
    target_tag = format_anon_id(target_id)

    # Cooldown check
    cd_until = scout_cooldowns.get((thief_id, target_id), 0.0)
    if cd_until > now:
        rem_min = int(cd_until - now) // 60 + 1
        msg = (
            f"⛔ <b>ТЫ НА СТРЕМЕ!</b>\n"
            f"Анон [<code>{target_tag}</code>] тебя уже спалил на шмоне и держит руку на кармане!\n"
            f"Подожди еще <b>{rem_min} мин.</b>, прежде чем снова совать к нему клешни!"
        )
        return False, msg, {"cooldown": True, "cooldown_left": cd_until - now}

    # Balance check and deduction (dynamic scout cost)
    from common.database import deduct_user_global_balance, get_user_global_balance, record_user_transaction
    thief_balance = await get_user_global_balance(db, thief_id)
    scout_cost = calculate_scout_cost(thief_balance)
    if thief_balance < scout_cost:
        msg = (
            f"❌ <b>НИЩИЙ РАЗВЕДЧИК!</b>\n"
            f"На проведение шмона и подкуп информаторов нужно <b>{scout_cost:,.0f} ₪</b>.\n"
            f"У тебя на руках всего <code>{thief_balance:,.2f} ₪</code>. Пиздуй работать на завод!"
        )
        return False, msg, {"insufficient_funds": True, "required_cost": scout_cost}

    ok_deduct, _ = await deduct_user_global_balance(db, thief_id, board_id, scout_cost)
    if not ok_deduct:
        return False, "❌ Ошибка списания средств на разведку.", {}

    await record_user_transaction(
        db, thief_id, -scout_cost, "scout_cost", f"Оплата шмона карманов анона {target_id}"
    )

    # Target state inspection
    target_items = await load_user_active_items(db, target_id, board_id)
    target_profile = get_criminal_profile(target_items)

    # 5G-Jammer stealth defense
    if target_profile["is_jammed"]:
        msg = (
            f"📡 <b>СИГНАЛ ЗАГЛУШЕН!</b>\n"
            f"У цели [<code>{target_tag}</code>] активирована подпольная <b>5G-глушилка</b>!\n"
            f"Все частоты забиты помехами и белым шумом. Шмон сорван, {scout_cost:,.0f} ₪ сгорели в эфире!"
        )
        return False, msg, {"jammed": True, "scout_cost": scout_cost}

    # Roll success (75% / 25%)
    if roll is None:
        roll = random.random()

    if roll >= 0.75:  # 25% FAIL
        scout_cooldowns[(thief_id, target_id)] = now + SCOUT_COOLDOWN_SEC
        spotted_phrase = random.choice(SCOUT_FAIL_SPOTTED_PHRASES)
        msg = (
            f"👀 <b>ПАЛЕВО НА ШМОНЕ!</b>\n"
            f"Анон [<code>{target_tag}</code>] вовремя обернулся и заметил вороватые клешни анона [<code>{thief_tag}</code>]:\n"
            f"<i>«{spotted_phrase}»</i>\n"
            f"🚨 Ты спалился! Повторный шмон этой цели заблокирован на <b>15 минут</b>!"
        )
        return False, msg, {"spotted": True, "cooldown_until": now + SCOUT_COOLDOWN_SEC}

    # 75% SUCCESS: disclose dossier
    target_balance = await get_user_global_balance(db, target_id)
    wealth_bracket = get_target_wealth_bracket(target_balance)
    armor_desc = detect_target_armor(target_items)
    traps = detect_target_traps(target_items, now=now)
    traps_desc = "\n".join(f"  • {t}" for t in traps) if traps else "  • Ловушек не обнаружено (карманы нараспашку)"
    scout_comment = random.choice(SCOUT_SUCCESS_COMMENTARY)

    msg = (
        f"🔍 <b>ДОСЬЕ ШМОНА: Анон [<code>{target_tag}</code>]</b>\n"
        f"🧐 <i>«{scout_comment}»</i>\n\n"
        f"💰 <b>Категория капитала:</b> {wealth_bracket}\n"
        f"🛡️ <b>Экипированная броня:</b> {armor_desc}\n"
        f"⚠️ <b>Обнаруженные ловушки:</b>\n"
        f"{traps_desc}\n\n"
        f"🗝️ <i>Совет щипача: проверь наличие отмычки перед срезом кошелька (/pickpocket)!</i>"
    )
    return True, msg, {
        "wealth_bracket": wealth_bracket,
        "armor": armor_desc,
        "traps": traps,
    }


# -----------------------------------------------------------------------------
# Core Mechanics: Pickpocket (/pickpocket, /карманник, /щипач)
# -----------------------------------------------------------------------------

async def execute_pickpocket(
    db: Any,
    thief_id: int,
    victim_id: int,
    board_id: str,
    roll: Optional[float] = None,
    pct: Optional[float] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes pickpocket theft:
    - Requires & consumes 1 lockpick.
    - Verifies victim beginner protection (<15 posts) & self-isolation.
    - Steals 4%..10% of victim wallet (max 25,000 ₪) -> dirty_balance.
    - Adds +1 wanted star and 5,000 ₪ bounty on thief.
    - 65% base success (higher if target sanity is low).
    - Success is SILENT in public chat. DM sent to thief.
    - Fail is LOUD in public chat: [Крыса] status for 2 hours + 2,000 ₪ penalty to victim.
    """
    now = time.time()
    thief_tag = format_anon_id(thief_id)
    victim_tag = format_anon_id(victim_id)

    thief_items = await load_user_active_items(db, thief_id, board_id)
    thief_profile = get_criminal_profile(thief_items)

    # 1. Lockpick requirement
    if thief_profile["lockpick"] < 1:
        msg = (
            f"🗝️ <b>НЕТ ОТМЫЧКИ!</b>\n"
            f"Чтобы ювелирно подрезать кошелёк в толпе, нужна воровская отмычка.\n"
            f"Загляни на подпольный Даркнет: <code>/darknet</code> (цена: 400 ₪)."
        )
        return False, msg, {"no_lockpick": True}

    # 2. Victim Beginner Protection & Isolation checks
    from common.database import (
        add_user_global_balance,
        deduct_user_global_balance,
        get_user_global_balance,
        record_user_transaction,
    )

    async with db.execute(
        "SELECT posts_count, COALESCE(is_isolated, 0) FROM Users WHERE user_id = ? AND board_id = ?",
        (victim_id, board_id),
    ) as cursor:
        row = await cursor.fetchone()

    posts_count = int(row[0] or 0) if row else 0
    is_isolated = bool(row[1] or 0) if row else False

    # Check shared_state isolation fallback
    try:
        import shared_state
        if shared_state.board_data.get(board_id, {}).get("user_settings", {}).get(victim_id, {}).get("is_isolated"):
            is_isolated = True
    except Exception:
        pass

    if posts_count < 15:
        msg = (
            f"🐣 <b>ЗАЩИТА НЬЮФАГА!</b>\n"
            f"У анона [<code>{victim_tag}</code>] меньше 15 постов в тредах.\n"
            f"Трогать свежих ньюфагов западло даже для дворовых щипачей! Отмычка спасена."
        )
        return False, msg, {"beginner_protected": True}

    if is_isolated:
        msg = (
            f"🧘 <b>ЦЕЛЬ В САМОИЗОЛЯЦИИ!</b>\n"
            f"Анон [<code>{victim_tag}</code>] заперся в бункере и ни с кем не контактирует.\n"
            f"Карманнику сюда не подлезть! Отмычка сохранена."
        )
        return False, msg, {"isolated": True}

    victim_balance = await get_user_global_balance(db, victim_id)
    if victim_balance <= 0:
        msg = (
            f"🪹 <b>У ЖЕРТВЫ ПУСТО!</b>\n"
            f"В карманах анона [<code>{victim_tag}</code>] только дырки и дохлая моль.\n"
            f"Срезать нечего! Отмычка сохранена."
        )
        return False, msg, {"empty_wallet": True}

    # Consume 1 lockpick
    thief_items["lockpick"] = thief_profile["lockpick"] - 1

    # 3. Defensive Traps Check: Pepperspray Defense & Chloroform Neutralization
    victim_items = await load_user_active_items(db, victim_id, board_id)
    has_pepperspray = bool(victim_items.get("pepperspray_gun") or (int(victim_items.get("pepperspray", 0) or 0) > 0))
    is_victim_chloroformed = float(victim_items.get("chloroformed_until", 0.0) or 0.0) > now

    if has_pepperspray and not is_victim_chloroformed:
        # Pepperspray triggers! Disables trap on victim, blinds thief
        if victim_items.get("pepperspray_gun"):
            victim_items["pepperspray_gun"] = False
        elif int(victim_items.get("pepperspray", 0) or 0) > 0:
            victim_items["pepperspray"] = max(0, int(victim_items.get("pepperspray", 0)) - 1)

        thief_items["peppersprayed_until"] = now + 1800.0  # 30 min blind debuff
        thief_items["rat_until"] = now + RAT_STATUS_DURATION_SEC
        penalty = PICKPOCKET_FAIL_PENALTY

        await deduct_user_global_balance(db, thief_id, board_id, penalty)
        await add_user_global_balance(db, victim_id, board_id, penalty)

        await save_user_active_items(db, thief_id, board_id, thief_items)
        await save_user_active_items(db, victim_id, board_id, victim_items)
        await record_user_transaction(
            db, thief_id, -penalty, "pickpocket_penalty", f"Штраф за попадание под перцовку жертвы {victim_id}"
        )
        await record_user_transaction(
            db, victim_id, penalty, "pickpocket_compensation", f"Компенсация от карманника {thief_id} за перцовку"
        )

        pepper_text = (
            f"🧯 <b>ПЕРЦОВАЯ СТРУЯ В ЕБЛО! САМООБОРОНА СРАБОТАЛА!</b>\n"
            f"Анон [<code>{thief_tag}</code>] попытался подрезать кошелек у анона [<code>{victim_tag}</code>], "
            f"но нарвался на боевой перцовый баллончик «Шпага»!\n\n"
            f"😵 Вор ослеплён едким газом на <b>30 минут</b>!\n"
            f"🏷️ Статус: <b>[Крыса]</b> на 2 часа!\n"
            f"💸 Компенсация: <b>{penalty:,.0f} ₪</b> выплачено бдительной жертве!\n"
            f"🗝️ Отмычка сломана о замок!"
        )
        return False, pepper_text, {
            "caught": True,
            "peppersprayed": True,
            "penalty": penalty,
            "rat_until": thief_items["rat_until"],
            "peppersprayed_until": thief_items["peppersprayed_until"],
            "lockpicks_left": thief_items["lockpick"],
        }

    # 4. Dynamic Success Rate based on Target Sanity & Master Key
    target_sanity = get_target_sanity_score(victim_items)
    sanity_bonus = max(0.0, min(0.20, (50 - target_sanity) * 0.005)) if target_sanity < 50 else 0.0

    has_master_key = int(thief_profile.get("master_key", 0) or 0) > 0 or int(thief_items.get("master_key", 0) or 0) > 0
    master_key_bonus = 0.20 if has_master_key else 0.0
    effective_success_rate = PICKPOCKET_BASE_SUCCESS + sanity_bonus + master_key_bonus

    if roll is None:
        roll = random.random()

    if roll < effective_success_rate:  # SUCCESS (SILENT)
        if pct is None:
            pct = random.uniform(PICKPOCKET_MIN_PCT, PICKPOCKET_MAX_PCT)
        raw_stolen = round(victim_balance * pct, 2)
        stolen = min(raw_stolen, PICKPOCKET_MAX_CAP)
        stolen = max(1.0, min(stolen, victim_balance))

        # Atomic balance & criminal ledger updates
        ok_victim, _ = await deduct_user_global_balance(db, victim_id, board_id, stolen)
        if ok_victim:
            add_dirty_shekels(thief_items, stolen)
            new_stars, new_bounty = add_wanted_stars(thief_items, stars=1, bounty=BOUNTY_PER_STAR)

            await save_user_active_items(db, thief_id, board_id, thief_items)
            await sync_user_criminal_status(db, thief_id, thief_items)
            await record_user_transaction(
                db, victim_id, -stolen, "theft_victim", f"Срез кошелька карманником {thief_id}"
            )
            await record_user_transaction(
                db, thief_id, stolen, "theft_dirty", f"Успешный карманный срез у анона {victim_id}"
            )

            silent_phrase = random.choice(PICKPOCKET_SILENT_SUCCESS_PHRASES)
            crowbar_note = "\n🗝️ <i>Медвежатницкая монтировка помогла обойти замки! (+20% шанс)</i>" if has_master_key else ""
            dm_text = (
                f"🤫 <b>ТИХИЙ КАРМАННЫЙ КРАЖ!</b>\n"
                f"<i>«{silent_phrase}»</i>\n\n"
                f"Ты ювелирно подрезал кошелёк у анона [<code>{victim_tag}</code>] в толпе треда!{crowbar_note}\n\n"
                f"💰 Срезано грязных шекелей: <b>+{stolen:,.2f} ₪</b>\n"
                f"⭐ Твой розыск: <b>{new_stars}★</b> (Баунти за твою голову: <code>{new_bounty:,.2f} ₪</code>)\n"
                f"🗝️ Осталось отмычек: <b>{thief_items['lockpick']}</b>\n\n"
                f"⚠️ <i>Шекели помечены как грязные! Отмывай их через синдикат или бойся дружинников!</i>"
            )
            return True, dm_text, {
                "silent": True,
                "stolen": stolen,
                "stars": new_stars,
                "bounty": new_bounty,
                "dirty_balance": thief_items.get("dirty_balance", 0.0),
                "lockpicks_left": thief_items["lockpick"],
                "has_master_key": has_master_key,
                "master_key_bonus": master_key_bonus,
                "effective_success_rate": effective_success_rate,
            }
        else:
            await save_user_active_items(db, thief_id, board_id, thief_items)
            return False, "❌ Ошибка вывода средств из кармана жертвы.", {}

    else:  # FAIL (LOUD)
        thief_items["rat_until"] = now + RAT_STATUS_DURATION_SEC
        penalty = PICKPOCKET_FAIL_PENALTY

        # Penalize thief, compensate victim
        await deduct_user_global_balance(db, thief_id, board_id, penalty)
        await add_user_global_balance(db, victim_id, board_id, penalty)

        await save_user_active_items(db, thief_id, board_id, thief_items)
        await record_user_transaction(
            db, thief_id, -penalty, "pickpocket_penalty", f"Штраф за провал карманной кражи у {victim_id}"
        )
        await record_user_transaction(
            db, victim_id, penalty, "pickpocket_compensation", f"Компенсация от пойманного карманника {thief_id}"
        )

        fail_phrase = random.choice(PICKPOCKET_LOUD_FAIL_PHRASES)
        loud_text = (
            f"🐀 <b>КРЫСА ПОЙМАНА С ПОЛИЧНЫМ!</b>\n"
            f"<i>«{fail_phrase}»</i>\n\n"
            f"Анон [<code>{thief_tag}</code>] пытался втихаря срезать кошелек у анона [<code>{victim_tag}</code>], "
            f"но обосрался на весь тред и застрял пальцами в чужом кармане!\n\n"
            f"🏷️ Статус: <b>[Крыса]</b> на 2 часа!\n"
            f"💸 Штраф на месте: <b>{penalty:,.0f} ₪</b> выплачено жертве за моральный ущерб!\n"
            f"🗝️ Отмычка сломана о замок!"
        )
        return False, loud_text, {
            "caught": True,
            "penalty": penalty,
            "rat_until": thief_items["rat_until"],
            "lockpicks_left": thief_items["lockpick"],
        }


# -----------------------------------------------------------------------------
# Core Mechanics: Arrest (/arrest, /принять, /задержать)
# -----------------------------------------------------------------------------

async def execute_arrest(
    db: Any,
    officer_id: int,
    criminal_id: int,
    board_id: str,
    fake_roll: Optional[float] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Executes arrest of wanted criminal:
    - Caller must hold badge_druzhinnik, ksiva_polkovnik, or fake_ksiva.
    - Target must have wanted_stars >= 1.
    - Fake Ksiva backfire (35%): caller fined 10,000 ₪ to Abu Fund and muted 30m.
    - Legit arrest: Criminal muted for stars * 15m (up to 75m).
    - Bounty split: 60% officer, 40% Abu Fund.
    - Confiscates criminal's заточки and lockpicks. Stars reset to 0.
    """
    now = time.time()
    officer_tag = format_anon_id(officer_id)
    criminal_tag = format_anon_id(criminal_id)

    officer_items = await load_user_active_items(db, officer_id, board_id)

    # Authority inspection
    has_druzhinnik = (
        float(officer_items.get("badge_druzhinnik_expires", 0.0) or 0.0) > now
        or bool(officer_items.get("badge_druzhinnik"))
    )
    has_ksiva = int(officer_items.get("ksiva_polkovnik", 0) or 0) > 0
    fake_raw = officer_items.get("fake_ksiva", 0)
    has_fake = (int(fake_raw or 0) > 0) if not isinstance(fake_raw, bool) else fake_raw

    if not (has_druzhinnik or has_ksiva or has_fake):
        msg = (
            f"🚫 <b>ТЫ КТО ТАКОЙ, ЧУХАН?!</b>\n"
            f"У тебя нет ни жетона дружинника, ни ксивы полковника! Кого ты задерживать собрался?\n"
            f"Пиздуй в <code>/shop</code> за жетоном или на <code>/darknet</code> за палёной ксивой!"
        )
        return False, msg, {"unauthorized": True}

    criminal_items = await load_user_active_items(db, criminal_id, board_id)
    criminal_profile = get_criminal_profile(criminal_items)

    if criminal_profile["wanted_stars"] < 1:
        msg = (
            f"🕊️ <b>ЧИСТ ПЕРЕД ЗАКОНОМ!</b>\n"
            f"У анона [<code>{criminal_tag}</code>] нет активных звёзд розыска (0★).\n"
            f"Дружинникам запрещено вязать законопослушных сычей!"
        )
        return False, msg, {"not_wanted": True}

    # Fake Ksiva backfire risk check (only if officer lacks legit authority)
    is_using_fake = has_fake and not (has_druzhinnik or has_ksiva)
    if is_using_fake:
        # Consume 1 fake ksiva
        if isinstance(officer_items.get("fake_ksiva"), int):
            officer_items["fake_ksiva"] = max(0, officer_items["fake_ksiva"] - 1)
        else:
            officer_items["fake_ksiva"] = 0

        if fake_roll is None:
            fake_roll = random.random()

        if fake_roll < FAKE_KSIVA_BACKFIRE_CHANCE:  # 35% BACKFIRE
            from common.database import (
                add_to_abu_fund,
                apply_regular_mute,
                deduct_user_global_balance,
                record_user_transaction,
            )

            # 1. Apply mute first (to ensure its internal transaction doesn't rollback pending queries)
            await apply_regular_mute(
                officer_id, board_id, FAKE_KSIVA_MUTE_SEC, reason="Попытка фальшивого ареста по палёной ксиве"
            )

            # 2. Fine caller and send proceeds to Abu Yacht Fund
            await deduct_user_global_balance(db, officer_id, board_id, FAKE_KSIVA_FINE)
            await add_to_abu_fund(db, FAKE_KSIVA_FINE, donor_id=officer_id, reason="fake_ksiva_fine")

            # 3. Persist active_items and record transaction
            await save_user_active_items(db, officer_id, board_id, officer_items)
            await record_user_transaction(
                db, officer_id, -FAKE_KSIVA_FINE, "fake_ksiva_fine", "Штраф за использование палёной ксивы"
            )

            backfire_text = (
                f"🚨 <b>ПАЛЁНАЯ КСИВА! Майор раскусил подделку!</b>\n"
                f"Анон [<code>{officer_tag}</code>] попытался задержать преступника по картонному удостоверению из перехода!\n"
                f"<i>«Ты кому эту туалетную бумагу суешь, щегол?! В дежурку его!»</i>\n\n"
                f"⚖️ <b>Приговор фальшивомонетчику:</b>\n"
                f"💸 Штраф: <b>{FAKE_KSIVA_FINE:,.0f} ₪</b> списано в Фонд Яхты Абу!\n"
                f"🔇 Мут: <b>30 минут</b> на бутылке правосудия!\n"
                f"🪪 Палёная ксива изъята и публично сожжена!"
            )
            return False, backfire_text, {
                "backfire": True,
                "fine": FAKE_KSIVA_FINE,
                "mute_sec": FAKE_KSIVA_MUTE_SEC,
            }

    # Legit arrest execution
    stars = criminal_profile["wanted_stars"]
    bounty = criminal_profile["bounty_pool"]
    jail_minutes = min(MAX_ARREST_MUTE_MINUTES, stars * 15)

    from common.database import (
        add_to_abu_fund,
        add_user_global_balance,
        apply_regular_mute,
        record_user_transaction,
    )

    # 1. Mute criminal
    await apply_regular_mute(
        criminal_id, board_id, jail_minutes * 60, reason=f"Арест дружинниками ({stars}★ розыска)"
    )

    # 2. Split bounty payout
    officer_payout = round(bounty * BOUNTY_OFFICER_SHARE, 2)
    abu_burn = round(bounty * BOUNTY_ABU_SHARE, 2)

    if officer_payout > 0:
        await add_user_global_balance(db, officer_id, board_id, officer_payout)
        await record_user_transaction(
            db, officer_id, officer_payout, "bounty_reward", f"Награда за поимку преступника {criminal_id} ({stars}★)"
        )
    if abu_burn > 0:
        await add_to_abu_fund(db, abu_burn, donor_id=criminal_id, reason=f"bounty_burn_{criminal_id}")

    # 3. Confiscate criminal inventory (lockpicks & zatochki)
    criminal_items["lockpick"] = 0
    criminal_items["knife"] = 0
    criminal_items["knife_gun"] = False
    criminal_items["zatochka"] = 0
    criminal_items["shank"] = 0

    # 4. Clear wanted status
    clear_wanted_status(criminal_items)

    await save_user_active_items(db, criminal_id, board_id, criminal_items)
    await sync_user_criminal_status(db, criminal_id, criminal_items)
    await save_user_active_items(db, officer_id, board_id, officer_items)
    await sync_user_criminal_status(db, officer_id, officer_items)

    druzhina_phrase = random.choice(ARREST_DRUZHINA_PHRASES)
    arrest_msg = (
        f"👮‍♂️ <b>ОБЛАВА ДРУЖИННИКОВ! ВОР В ЗАКОНЕ ПРИНЯТ!</b>\n"
        f"<i>«{druzhina_phrase}»</i>\n\n"
        f"Офицер [<code>{officer_tag}</code>] жестко положил преступника [<code>{criminal_tag}</code>] ({stars}★) мордой в асфальт!\n\n"
        f"🔒 <b>Приговор суда:</b> <b>{jail_minutes} минут</b> в КПЗ (полный мут)!\n"
        f"💰 <b>Награда за голову:</b> <code>{bounty:,.2f} ₪</code>\n"
        f"  ├ Офицеру: <b>+{officer_payout:,.2f} ₪</b> (60%)\n"
        f"  └ Фонд Яхты Абу: <b>+{abu_burn:,.2f} ₪</b> (40%)\n"
        f"📦 <b>Конфискация:</b> Все отмычки и заточки изъяты протоколом досмотра!\n\n"
        f"Бутылка правосудия настигла виновного!"
    )
    return True, arrest_msg, {
        "officer_payout": officer_payout,
        "abu_burn": abu_burn,
        "jail_minutes": jail_minutes,
        "confiscated": True,
        "stars": stars,
    }


# -----------------------------------------------------------------------------
# Darknet Syndicate Purchasing Helper
# -----------------------------------------------------------------------------

async def handle_darknet_item_buy(
    db: Any,
    user_id: int,
    board_id: str,
    item_id: str,
    balance: Optional[float] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Handles purchase of items from the Darknet Syndicate catalog.
    Validates item, checks/deducts shekel balance with dynamic pricing,
    updates active_items, and records tx.
    """
    canonical_id = resolve_darknet_item_id(item_id)
    if not canonical_id or canonical_id not in DARKNET_CATALOG:
        return (
            False,
            f"❌ Неизвестный товар Даркнета: <code>{item_id}</code>.\n"
            f"Доступный ассортимент: <code>lockpick</code> (отмычка), <code>fake_ksiva</code> (палёная ксива), "
            f"<code>jammer</code> (глушилка), <code>master_key</code> (монтировка), <code>bribe_envelope</code> (взятка), "
            f"<code>chloroform</code> (хлороформ).",
            {},
        )

    item_id = canonical_id
    item = DARKNET_CATALOG[item_id]
    item_name = item["name"]

    from common.database import deduct_user_global_balance, get_user_global_balance, record_user_transaction
    from common.db_pool import db_transaction

    async with db_transaction(db):
        if balance is None:
            balance = await get_user_global_balance(db, user_id)

        price = float(get_darknet_item_price(item_id, balance))

        withdrawn_bank = 0.0
        # Если не хватает налички в кошельке, но покупается товар для сброса розыска:
        # используем исключение и списываем средства из Банка Абу (ликвидация deadlock)
        if balance < price and canonical_id in ("bribe_envelope", "fake_passport", "lawyer"):
            try:
                from bank_engine import get_user_bank_summary, withdraw_bank_deposit
                _, _, deposits = await get_user_bank_summary(db, user_id)
                active_deps = [d for d in deposits if d.get("status") == "active"]
                active_deps.sort(key=lambda d: 0 if not d.get("is_locked") else 1)
                needed = price - balance
                for dep in active_deps:
                    if withdrawn_bank >= needed:
                        break
                    ok_wd, payout, _, _, _, _, _ = await withdraw_bank_deposit(
                        db, dep["id"], user_id, board_id, force_early=True, allow_bribe_bypass=True
                    )
                    if ok_wd and payout > 0:
                        withdrawn_bank += payout
                if withdrawn_bank > 0:
                    balance = await get_user_global_balance(db, user_id)
            except Exception as e:
                logger.warning(f"Error drawing from bank deposit for darknet buy: {e}")

        if balance < price:
            missing = price - balance
            msg = (
                f"⚠️ <b>НЕДОСТАТОЧНО ШЕКЕЛЕЙ!</b>\n\n"
                f"Для покупки {item_name} требуется: <b>{price:,.0f} ₪</b>.\n"
                f"💵 Твой баланс: <code>{balance:,.2f} ₪</code>.\n"
                f"❗ Не хватает: <b>{missing:,.2f} ₪</b>.\n\n"
                f"💡 Заработай недостающую сумму на заводе (<code>/work</code>) или сбрось розыск по таймеру отсидки!"
            )
            return False, msg, {"insufficient_funds": True, "required": price, "balance": balance, "missing": missing}

        ok_deduct, _ = await deduct_user_global_balance(db, user_id, board_id, price)
        if not ok_deduct:
            return False, "❌ Ошибка списания средств за покупку на Даркнете.", {}

        active_items = await load_user_active_items(db, user_id, board_id)
        now = time.time()
        extra_note = ""

        if item_id == "lockpick":
            active_items["lockpick"] = int(active_items.get("lockpick", 0) or 0) + 1
        elif item_id == "fake_ksiva":
            active_items["fake_ksiva"] = int(active_items.get("fake_ksiva", 0) or 0) + 1
        elif item_id == "jammer":
            curr_jammer = float(active_items.get("jammer_until", 0.0) or 0.0)
            active_items["jammer_until"] = max(curr_jammer, now) + float(item.get("duration", 3600.0))
        elif item_id == "master_key":
            active_items["master_key"] = int(active_items.get("master_key", 0) or 0) + 1
        elif item_id == "bribe_envelope":
            active_items["bribe_envelope"] = int(active_items.get("bribe_envelope", 0) or 0) + 1
        elif item_id == "chloroform":
            active_items["chloroform"] = int(active_items.get("chloroform", 0) or 0) + 1
        elif item_id == "fake_passport":
            active_items["fake_passport"] = int(active_items.get("fake_passport", 0) or 0) + 1
            # Сброс розыска при активации новых документов
            curr_stars = int(active_items.get("wanted_stars", 0) or 0)
            if curr_stars > 0:
                clear_wanted_status(active_items)
                await sync_user_criminal_status(db, user_id, active_items)
                extra_note = "\n🪪 <b>Личность изменена: все звёзды розыска сняты (0★)! Счета разблокированы.</b>"
        elif item_id == "lawyer":
            active_items["lawyer"] = int(active_items.get("lawyer", 0) or 0) + 1
            curr_stars = int(active_items.get("wanted_stars", 0) or 0)
            if curr_stars > 0:
                drop = min(3, curr_stars)
                new_s = max(0, curr_stars - drop)
                curr_bp = float(active_items.get("bounty_pool") or 0.0)
                new_bp = max(0.0, round(curr_bp * (new_s / curr_stars), 2)) if new_s > 0 else 0.0
                active_items["wanted_stars"] = new_s
                active_items["bounty_pool"] = new_bp
                active_items["bounty"] = new_bp
                await sync_user_criminal_status(db, user_id, active_items)
                extra_note = f"\n⚖️ <b>Адвокат обжаловал арест: -{drop}★ розыска! Текущий уровень: {new_s}★.</b>"
                if curr_stars >= 5 and new_s < 5:
                    extra_note += "\n🔓 <b>Банковские счета разблокированы!</b>"
            # Снимаем арест в Mutes если был
            try:
                await db.execute(
                    "DELETE FROM Mutes WHERE user_id = ? AND (mute_type = 'arrest' OR reason LIKE '%арест%' OR reason LIKE '%Арест%')",
                    (user_id,)
                )
                if hasattr(db, "commit"):
                    await db.commit()
            except Exception:
                pass

        await save_user_active_items(db, user_id, board_id, active_items)
        tx_desc = f"Покупка {item_name} на подпольном Даркнете"
        if withdrawn_bank > 0:
            tx_desc += " (списание из Банка Абу по спец-исключению)"
        await record_user_transaction(db, user_id, -price, "darknet_buy", tx_desc)

    bank_source_note = f"\n🏦 <i>Оплачено со спецсчёта Банка Абу ({withdrawn_bank:,.0f} ₪ в обход ареста).</i>" if withdrawn_bank > 0 else ""
    success_msg = (
        f"🕶️ <b>ПОДПОЛЬНАЯ СДЕЛКА СОВЕРШЕНА!</b>\n"
        f"Ты приобрёл <b>{item_name}</b> за <code>{price:,.0f} ₪</code>!\n"
        f"Товар доставлен в твой инвентарь.{extra_note}{bank_source_note}"
    )
    return True, success_msg, active_items


# -----------------------------------------------------------------------------
# Aiogram Message Handlers
# -----------------------------------------------------------------------------

@criminal_router.message(Command("scout", "шмон", "разведка", ignore_case=True, ignore_mention=True))
async def cmd_scout(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /scout, /шмон, /разведка.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    target_id = await safe_resolve_target(message)
    if not target_id:
        await message.answer(
            "👀 <b>КОГО ШМОНАТЬ-ТО, СЫЧ?</b>\n"
            "Ответь <b>реплаем</b> на сообщение жертвы в треде, чтобы заглянуть в её карманы!",
            parse_mode="HTML",
        )
        return

    if target_id == user_id:
        await message.answer(
            "🤡 <b>ТЫ ЕБАНУЛСЯ?</b> Ты суешь клешни в собственные карманы и щупаешь свои фаберже. Ответь реплаем на чужой пост!",
            parse_mode="HTML",
        )
        return

    from common.db_pool import get_pool
    db = await get_pool()

    _, report, _ = await execute_scout(db, user_id, target_id, board_id)
    await message.answer(report, parse_mode="HTML")


@criminal_router.message(Command("pickpocket", "карманник", "щипач", ignore_case=True, ignore_mention=True))
async def cmd_pickpocket(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /pickpocket, /карманник, /щипач.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    target_id = await safe_resolve_target(message)
    if not target_id:
        await message.answer(
            "🧤 <b>КОГО ЩИПАТЬ-ТО, ДОЛБОЁБ?</b>\n"
            "Ответь <b>реплаем</b> на сообщение жертвы в треде, чтобы незаметно срезать кошелёк!",
            parse_mode="HTML",
        )
        return

    if target_id == user_id:
        await message.answer(
            "🤡 Ты пытаешься обчистить сам себя? Ебать ты гений, позвони в дурку.",
            parse_mode="HTML",
        )
        return

    from common.db_pool import get_pool
    db = await get_pool()

    is_success, reply_text, meta = await execute_pickpocket(db, user_id, target_id, board_id)

    if is_success and meta.get("silent"):
        # Silent success in public chat: delete command message to avoid trace
        try:
            await message.delete()
        except Exception:
            pass

        # Send private DM to thief
        from common.bot_helpers import send_pvp_direct_notification
        delivered = await send_pvp_direct_notification(message.bot, user_id, reply_text)
        if not delivered:
            # Fallback if bot cannot initiate DM (e.g. thief blocked bot)
            try:
                temp_msg = await message.answer("🤫 <i>(Кошелёк срезан ювелирно и без шума...)</i>", parse_mode="HTML")
                await asyncio.sleep(4)
                await temp_msg.delete()
            except Exception:
                pass
    else:
        # Loud public failure or validation warning
        await message.answer(reply_text, parse_mode="HTML")


@criminal_router.message(Command("arrest", "принять", "задержать", ignore_case=True, ignore_mention=True))
async def cmd_arrest(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /arrest, /принять, /задержать.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    target_id = await safe_resolve_target(message)
    if not target_id:
        await message.answer(
            "👮 <b>ПРИЕМ НА МЕСТЕ!</b>\n"
            "Ответь <b>реплаем</b> на сообщение преступника, чтобы провести задержание!",
            parse_mode="HTML",
        )
        return

    if target_id == user_id:
        await message.answer(
            "🤡 Ты решил надеть наручники на самого себя? Вызывайте санитаров!",
            parse_mode="HTML",
        )
        return

    from common.db_pool import get_pool
    db = await get_pool()

    _, result_text, _ = await execute_arrest(db, user_id, target_id, board_id)
    await message.answer(result_text, parse_mode="HTML")


def build_darknet_keyboard(balance: float) -> InlineKeyboardMarkup:
    """
    Builds the interactive inline keyboard for /darknet with dynamic price buttons:
    - [🗝️ Отмычка ({p_lock} ₪)], [🪪 Палёная ксива ({p_ksiva} ₪)]
    - [📡 5G-Глушилка ({p_jam} ₪)], [🗝️ Монтировка ({p_mkey} ₪)]
    - [✉️ Взятка следаку ({p_bribe} ₪)], [🧪 Хлороформ ({p_chlor} ₪)]
    - [🔄 Обновить], [🛒 Обычный магазин (/shop)]
    """
    p_lock = get_darknet_item_price("lockpick", balance)
    p_ksiva = get_darknet_item_price("fake_ksiva", balance)
    p_jam = get_darknet_item_price("jammer", balance)
    p_mkey = get_darknet_item_price("master_key", balance)
    p_bribe = get_darknet_item_price("bribe_envelope", balance)
    p_chlor = get_darknet_item_price("chloroform", balance)
    p_pass = get_darknet_item_price("fake_passport", balance)
    p_lawyer = get_darknet_item_price("lawyer", balance)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🗝️ Отмычка ({p_lock:,} ₪)", callback_data="darknet_buy_lockpick"),
                InlineKeyboardButton(text=f"🪪 Палёная ксива ({p_ksiva:,} ₪)", callback_data="darknet_buy_fake_ksiva"),
            ],
            [
                InlineKeyboardButton(text=f"📡 5G-Глушилка ({p_jam:,} ₪)", callback_data="darknet_buy_jammer"),
                InlineKeyboardButton(text=f"🗝️ Монтировка ({p_mkey:,} ₪)", callback_data="darknet_buy_master_key"),
            ],
            [
                InlineKeyboardButton(text=f"✉️ Взятка следаку ({p_bribe:,} ₪)", callback_data="darknet_buy_bribe_envelope"),
                InlineKeyboardButton(text=f"🧪 Хлороформ ({p_chlor:,} ₪)", callback_data="darknet_buy_chloroform"),
            ],
            [
                InlineKeyboardButton(text=f"🪪 Паспорт ({p_pass:,} ₪)", callback_data="darknet_buy_fake_passport"),
                InlineKeyboardButton(text=f"⚖️ Адвокат ({p_lawyer:,} ₪)", callback_data="darknet_buy_lawyer"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="darknet_refresh"),
                InlineKeyboardButton(text="🛒 Обычный магазин (/shop)", callback_data="darknet_open_shop"),
            ],
        ]
    )


def build_darknet_menu_text(balance: float, user_items: Optional[Dict[str, Any]] = None) -> str:
    """
    Builds the rich HTML text for /darknet catalog.
    """
    profile = get_criminal_profile(user_items) if user_items else None
    lines = [
        "🕶️ <b>ТЕНЕВОЙ РЫНОК /b/ (DARKNET SYNDICATE)</b>",
        "<i>Добро пожаловать в подпольный криминальный хаб. Здесь продаются запрещенные инструменты:</i>\n",
        f"💵 <b>Твой баланс:</b> <code>{balance:,.2f} ₪</code>",
    ]
    if profile:
        lines.append(
            f"⭐ Розыск: <b>{profile['wanted_stars']}★</b> | "
            f"💰 Баунти: <code>{profile['bounty_pool']:,.0f} ₪</code> | "
            f"🧤 Грязные: <code>{profile['dirty_balance']:,.0f} ₪</code>"
        )
        inv_parts = []
        if profile["lockpick"] > 0:
            inv_parts.append(f"🗝️ Отмычки: {profile['lockpick']}")
        if profile["fake_ksiva"] > 0:
            inv_parts.append(f"🪪 Ксива: {profile['fake_ksiva']}")
        if profile.get("master_key", 0) > 0:
            inv_parts.append(f"🗝️ Монтировка: {profile['master_key']}")
        if profile.get("bribe_envelope", 0) > 0:
            inv_parts.append(f"✉️ Конверты: {profile['bribe_envelope']}")
        if profile.get("chloroform", 0) > 0:
            inv_parts.append(f"🧪 Хлороформ: {profile['chloroform']}")
        if profile.get("fake_passport", 0) > 0:
            inv_parts.append(f"🪪 Паспорт: {profile['fake_passport']}")
        if profile.get("lawyer", 0) > 0:
            inv_parts.append(f"⚖️ Адвокат: {profile['lawyer']}")
        if profile["is_jammed"]:
            rem = int(profile["jammer_until"] - time.time()) // 60 + 1
            inv_parts.append(f"📡 Глушилка: {rem}м")
        if inv_parts:
            lines.append("🎒 <b>Твой воровской инвентарь:</b> " + ", ".join(inv_parts))

    lines.append("\n<b>Ассортимент каталога:</b>")
    for key, item in DARKNET_CATALOG.items():
        price = get_darknet_item_price(key, balance)
        lines.append(f"<b>{item['name']}</b> — <code>{price:,.0f} ₪</code>")
        lines.append(f"└ {item['desc']}")
        lines.append(f"🛒 <i>Купить:</i> <code>/buy_darknet {key}</code>\n")

    lines.append("⚠️ <i>Все сделки окончательны. Нажмите кнопку ниже для моментальной покупки:</i>")
    return "\n".join(lines)


@criminal_router.message(Command("darknet", "даркнет", ignore_case=True, ignore_mention=True))
async def cmd_darknet(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /darknet catalog display with interactive dynamic buttons.
    Supports /darknet buy <item> or /darknet <item> directly!
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    raw_text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    parts = raw_text.strip().split()
    if len(parts) >= 2:
        arg_start = 2 if parts[1].lower() in ("buy", "купить", "взять", "заказать", "приобрести") else 1
        query_item = " ".join(parts[arg_start:]).strip()
        if query_item:
            from common.db_pool import get_pool
            db = await get_pool()
            _, reply_text, _ = await handle_darknet_item_buy(db, user_id, board_id, query_item)
            await message.answer(reply_text, parse_mode="HTML")
            return

    from common.db_pool import get_pool
    db = await get_pool()
    from common.database import get_user_global_balance
    bal = await get_user_global_balance(db, user_id)
    items = await load_user_active_items(db, user_id, board_id)

    text = build_darknet_menu_text(bal, items)
    kb = build_darknet_keyboard(bal)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


def _is_media_message(message: Any) -> bool:
    if not message:
        return False
    photo = getattr(message, "photo", None)
    if photo is not None and (not (type(photo).__name__ == "MagicMock") or isinstance(photo, (list, tuple))):
        return bool(photo)
    video = getattr(message, "video", None)
    if video is not None and (not (type(video).__name__ == "MagicMock")):
        return bool(video)
    caption = getattr(message, "caption", None)
    if caption is not None and (not (type(caption).__name__ == "MagicMock") or isinstance(caption, str)):
        return bool(caption)
    return False


async def _update_darknet_or_banner_message(
    message: Optional[types.Message],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    """
    Safely updates a message with new text and keyboard whether it is a photo/media banner
    (using edit_caption or deleting and answering if caption > 1024) or a plain text message
    (using edit_text). Returns True if message was modified/sent, False if unmodified or unavailable.
    """
    if not message:
        return False

    has_media = _is_media_message(message)

    if has_media:
        if len(text) <= 1024:
            try:
                if hasattr(message, "edit_caption"):
                    res = message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
                    if inspect.isawaitable(res):
                        await res
                    return True
            except TelegramBadRequest as ex:
                if "message is not modified" in str(ex).lower():
                    return False
            except Exception:
                pass

        try:
            if hasattr(message, "delete"):
                res = message.delete()
                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass
        if hasattr(message, "answer"):
            res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
            if inspect.isawaitable(res):
                await res
        return True
    else:
        try:
            if hasattr(message, "edit_text"):
                res = message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
                return True
        except TelegramBadRequest as ex:
            if "message is not modified" in str(ex).lower():
                return False
            try:
                if hasattr(message, "delete"):
                    res = message.delete()
                    if inspect.isawaitable(res):
                        await res
            except Exception:
                pass
            if hasattr(message, "answer"):
                res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
            return True
        except Exception:
            try:
                if hasattr(message, "delete"):
                    res = message.delete()
                    if inspect.isawaitable(res):
                        await res
            except Exception:
                pass
            if hasattr(message, "answer"):
                res = message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
                if inspect.isawaitable(res):
                    await res
            return True


@criminal_router.callback_query(F.data.startswith("darknet_buy_"))
async def cb_darknet_buy(callback_query: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Interactive inline button handler for darknet purchasing with exception safety.
    """
    try:
        user_id = callback_query.from_user.id if callback_query.from_user else 0
        if not user_id:
            await callback_query.answer("❌ Ошибка авторизации.", show_alert=True)
            return

        if not board_id:
            board_id = getattr(callback_query.message, "board_id", None) or "b"

        item_id = callback_query.data[len("darknet_buy_"):].strip().lower()

        from common.db_pool import get_pool
        db = await get_pool()

        ok, reply_text, active_items = await handle_darknet_item_buy(db, user_id, board_id, item_id)

        from common.database import get_user_global_balance
        new_bal = await get_user_global_balance(db, user_id)

        if ok:
            await callback_query.answer("✅ Товар успешно куплен!", show_alert=False)
            try:
                new_text = build_darknet_menu_text(new_bal, active_items)
                new_kb = build_darknet_keyboard(new_bal)
                await _update_darknet_or_banner_message(callback_query.message, new_text, new_kb)
            except Exception:
                pass
        else:
            clean_text = re.sub(r"<[^>]+>", "", reply_text)[:190]
            await callback_query.answer(clean_text, show_alert=True)
    except Exception as e:
        logger.error(f"[cb_darknet_buy] Error: {e}", exc_info=True)
        try:
            from common.bot_helpers import safe_callback_answer
            await safe_callback_answer(callback_query, "❌ Ошибка при покупке на Даркнете.", show_alert=True)
        except Exception:
            pass


@criminal_router.callback_query(F.data == "darknet_hub")
async def cb_darknet_hub(callback_query: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Navigation handler for opening the Darknet catalog hub.
    Transitions seamlessly without emitting false 'Каталог уже актуален' toasts.
    """
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not user_id:
        from common.bot_helpers import safe_callback_answer
        await safe_callback_answer(callback_query)
        return

    if not board_id:
        board_id = getattr(callback_query.message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()
    from common.database import get_user_global_balance
    bal = await get_user_global_balance(db, user_id)
    items = await load_user_active_items(db, user_id, board_id)

    text = build_darknet_menu_text(bal, items)
    kb = build_darknet_keyboard(bal)
    from common.bot_helpers import render_menu_transition
    await render_menu_transition(callback_query, text, kb, prefer_banner=False)


@criminal_router.callback_query(F.data == "darknet_refresh")
async def cb_darknet_refresh(callback_query: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Explicit refresh button handler inside /darknet menu.
    """
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    if not user_id:
        from common.bot_helpers import safe_callback_answer
        await safe_callback_answer(callback_query)
        return

    if not board_id:
        board_id = getattr(callback_query.message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()
    from common.database import get_user_global_balance
    new_bal = await get_user_global_balance(db, user_id)
    items = await load_user_active_items(db, user_id, board_id)

    new_text = build_darknet_menu_text(new_bal, items)
    new_kb = build_darknet_keyboard(new_bal)
    from common.bot_helpers import safe_callback_answer
    modified = await _update_darknet_or_banner_message(callback_query.message, new_text, new_kb)
    if modified:
        await safe_callback_answer(callback_query, "🔄 Каталог обновлен!")
    else:
        await safe_callback_answer(callback_query, "Каталог уже актуален.")


@criminal_router.callback_query(F.data == "darknet_open_shop")
async def cb_darknet_open_shop(callback_query: types.CallbackQuery, board_id: Optional[str] = None):
    """
    Redirect button to /shop or shop hub. Transitions seamlessly to main shop banner.
    """
    if not board_id:
        board_id = getattr(callback_query.message, "board_id", None) or "b"

    user_id = callback_query.from_user.id if callback_query.from_user else 0
    from common.db_pool import get_pool
    db = await get_pool()
    from common.database import get_user_global_balance
    bal = await get_user_global_balance(db, user_id)

    try:
        from main import cb_shop_main_hub
        await cb_shop_main_hub(callback_query, board_id=board_id)
        return
    except Exception:
        pass

    try:
        from main import cb_prof_shop
        await cb_prof_shop(callback_query, board_id=board_id)
        return
    except Exception:
        pass

    try:
        from main import _build_main_shop_hub
        from common.bot_helpers import render_menu_transition
        text, kb = _build_main_shop_hub(user_id, bal)
        await render_menu_transition(callback_query, text, kb, category="shop", prefer_banner=True)
        return
    except Exception:
        pass

    await callback_query.answer()
    if callback_query.message:
        await callback_query.message.answer(
            "🛒 Для перехода в легальный магазин используй команду <code>/shop</code>.",
            parse_mode="HTML",
        )


@criminal_router.message(
    Command(
        "buy_darknet",
        "darknet_buy",
        "даркнет_купить",
        "купить_даркнет",
        "buy_dark",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_buy_darknet(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /buy_darknet <item_id> (supports multi-word phrases, English & Russian aliases).
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    parts = message.text.strip().split() if message.text else []
    if len(parts) < 2:
        help_msg = (
            "🕶️ <b>ПОДПОЛЬНЫЙ ДАРКНЕТ: СПРАВКА ПО ПОКУПКЕ</b>\n\n"
            "Укажи идентификатор или название товара для покупки:\n"
            "<code>/buy_darknet &lt;товар&gt;</code>\n\n"
            "📦 <b>Доступный ассортимент синдиката:</b>\n"
            "• 🗝️ <code>lockpick</code> (отмычка) — инструмент вора-карманника (/pickpocket)\n"
            "• 🪪 <code>fake_ksiva</code> (палёная ксива) — арест беглецов (/arrest)\n"
            "• 📡 <code>jammer</code> (5G-глушилка) — блокировка слежки на 1 час (/scout)\n"
            "• 🗝️ <code>master_key</code> (монтировка) — +20% к успеху взломов и краж\n"
            "• ✉️ <code>bribe_envelope</code> (конверт со взяткой) — сброс 1★ розыска (/bribe_cop)\n"
            "• 🧪 <code>chloroform</code> (хлороформ) — усыпление жертвы на 30 мин (/chloroform)\n\n"
            "💡 <b>Примеры покупки:</b>\n"
            "  ├ <code>/buy_darknet отмычка</code>\n"
            "  ├ <code>/buy_darknet ксива</code>\n"
            "  ├ <code>/buy_darknet глушилка</code>\n"
            "  ├ <code>/buy_darknet монтировка</code>\n"
            "  ├ <code>/buy_darknet конверт со взяткой</code>\n"
            "  └ <code>/buy_darknet хлороформ</code>\n\n"
            "🛒 Интерактивный каталог с кнопками: <code>/darknet</code>"
        )
        await message.answer(help_msg, parse_mode="HTML")
        return

    raw_item = " ".join(parts[1:]).strip()
    from common.db_pool import get_pool
    db = await get_pool()

    _, reply_text, _ = await handle_darknet_item_buy(db, user_id, board_id, raw_item)
    await message.answer(reply_text, parse_mode="HTML")


# -----------------------------------------------------------------------------
# New Syndicate Mechanics: /bribe_cop, /wanted, /jail & /chloroform
# -----------------------------------------------------------------------------

async def execute_bribe_cop(
    db: Any,
    user_id: int,
    board_id: str,
    clear_all: bool = False,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Дача взятки следователю для снижения или полного сброса звёзд розыска.
    Поддерживает:
    1) Конверты со взяткой (bribe_envelope) из Даркнета.
    2) Магазинную индульгенцию (bribe) из обычного /shop.
    3) Прямую оплату наличными шекелями (динамический прайс), предотвращая софтлок при заблокированном банке.
    4) Синхронизацию статуса розыска по всем бордам в Users.
    """
    user_items = await load_user_active_items(db, user_id, board_id)
    profile = get_criminal_profile(user_items)
    stars = profile["wanted_stars"]

    envelopes = int(user_items.get("bribe_envelope", 0) or 0)
    shop_bribes = int(user_items.get("bribe", 0) or 0)

    from common.database import (
        get_user_global_balance,
        deduct_user_global_balance,
        record_user_transaction,
        add_to_abu_fund,
    )
    balance = await get_user_global_balance(db, user_id)

    if stars < 1:
        msg = (
            "🕊️ <b>ЧИСТ ПЕРЕД ЗАКОНОМ!</b>\n"
            "У тебя нет активных звёзд розыска (0★)! Некому и незачем совать взятку."
        )
        return False, msg, {"not_wanted": True}

    stars_to_clear = stars if clear_all else 1

    payment_method = None
    cost_paid = 0.0

    if envelopes >= 1:
        # Приоритет 1: Конверт со взяткой
        if clear_all:
            envelopes_used = min(envelopes, stars_to_clear)
            user_items["bribe_envelope"] = envelopes - envelopes_used
            stars_to_clear = envelopes_used
            fluff = f"Майор сгреб {envelopes_used} конвертов со взяткой и пустил уголовные дела под шредер!"
            payment_info = f"✉️ Использовано конвертов со взяткой: <b>{envelopes_used} шт.</b> (осталось: <b>{user_items['bribe_envelope']}</b>)"
        else:
            user_items["bribe_envelope"] = envelopes - 1
            fluff = "Майор ловким движением руки смахнул пухлый конверт в ящик стола и «случайно» пролил кофе на твое уголовное дело!"
            payment_info = f"✉️ Использован 1 конверт со взяткой (осталось: <b>{user_items['bribe_envelope']}</b>)"
        payment_method = "bribe_envelope"

    elif shop_bribes >= 1:
        # Приоритет 2: Магазинная индульгенция из /shop
        if clear_all:
            bribes_used = min(shop_bribes, stars_to_clear)
            user_items["bribe"] = shop_bribes - bribes_used
            stars_to_clear = bribes_used
            fluff = f"Следователь скептически повертел в руках магазинные индульгенции ({bribes_used} шт.): <i>«Ладно, на первый раз сойдёт, сыч!»</i>"
            payment_info = f"📜 Использовано магазинных индульгенций: <b>{bribes_used} шт.</b> (осталось: <b>{user_items['bribe']}</b>)"
        else:
            user_items["bribe"] = shop_bribes - 1
            fluff = "Следователь скептически повертел в руках простую магазинную индульгенцию: <i>«Ладно, на первый раз сойдёт, сыч!»</i>"
            payment_info = f"📜 Использована магазинная индульгенция (осталось: <b>{user_items['bribe']}</b>)"
        payment_method = "shop_bribe"

    else:
        # Приоритет 3: Прямая оплата шекелями (скидка 10% за опт при /bribe_cop all или >1★)
        price_per_star = get_darknet_item_price("bribe_envelope", balance)
        total_cost = float(price_per_star * stars_to_clear)
        if clear_all or stars_to_clear > 1:
            total_cost = round(total_cost * 0.90, 2)  # Скидка 10% за оптовый сброс

        bank_withdrawn_sum = 0.0
        used_deposits = []
        if balance < total_cost:
            # Спец-исключение для снятия блокировки: списание из депозитов Банка Абу (ликвидация deadlock)
            try:
                from bank_engine import get_user_bank_summary, withdraw_bank_deposit
                _, _, deposits = await get_user_bank_summary(db, user_id)
                active_deps = [d for d in deposits if d.get("status") == "active"]
                # Сначала используем разблокированные, затем остальные
                active_deps.sort(key=lambda d: 0 if not d.get("is_locked") else 1)
                needed = total_cost - balance

                for dep in active_deps:
                    if bank_withdrawn_sum >= needed:
                        break
                    ok_wd, payout, princ, interest, fee, is_def, err = await withdraw_bank_deposit(
                        db, dep["id"], user_id, board_id, force_early=True, allow_bribe_bypass=True
                    )
                    if ok_wd and payout > 0:
                        bank_withdrawn_sum += payout
                        used_deposits.append(dep["id"])

                if bank_withdrawn_sum > 0:
                    balance = await get_user_global_balance(db, user_id)
            except Exception as e:
                logger.warning(f"Failed to withdraw from bank for bribe: {e}")

        if balance < total_cost:
            missing = total_cost - balance
            msg = (
                "✉️ <b>НЕТ КОНВЕРТА С ВЗЯТКОЙ!</b>\n"
                "У тебя нет конверта для следователя, а шекелей в кошельке и на счетах Банка не хватает!\n"
                f"Майор требует за закрытие дела: <b>{total_cost:,.0f} ₪</b>.\n"
                f"💵 Твой баланс: <code>{balance:,.2f} ₪</code>.\n"
                f"❗ Не хватает: <b>{missing:,.2f} ₪</b>.\n\n"
                "💡 <i>Как решить проблему:</i>\n"
                "• Заработай шекели на сменах: <code>/work</code>\n"
                "• Нанять адвоката для апелляции: <code>/lawyer</code>\n"
                "• Сменить документы: <code>/fake_passport</code> или в <code>/darknet</code>\n"
                "• Сдаться с повинной и отсидеть короткий срок: <code>/surrender</code>\n"
                "• Или подождать 30 минут — звёзды розыска спадают автоматически по таймеру!"
            )
            return False, msg, {"no_envelope": True, "insufficient_funds": True, "required": total_cost, "balance": balance, "missing": missing}

        ok_ded, _ = await deduct_user_global_balance(db, user_id, board_id, total_cost)
        if not ok_ded:
            return False, "❌ Ошибка списания средств на взятку следователю.", {}

        cost_paid = total_cost
        payment_method = "shekels_bank" if bank_withdrawn_sum > 0 else "shekels"
        if bank_withdrawn_sum > 0:
            fluff = f"Майор провёл безналичный транзит со счёта Банка Абу (вклады #{', #'.join(map(str, used_deposits))}) на сумму <b>{total_cost:,.0f} ₪</b> и сжёг постановление!"
            payment_info = f"🏦 Оплачено через транзитный счёт Банка Абу: <b>{total_cost:,.0f} ₪</b> (сняты арестованные средства)"
        else:
            fluff = f"Майор пересчитал пачку хрустящих купюр (<b>{total_cost:,.0f} ₪</b>) под столом, удовлетворённо крякнул и сжёг протокол!"
            discount_note = " <i>(с учетом оптовой скидки 10%)</i>" if (clear_all or stars_to_clear > 1) else ""
            payment_info = f"💵 Оплачено шекелями: <b>{total_cost:,.0f} ₪</b>{discount_note} (списано из кошелька)"

        # Откат 50% в Фонд Яхты Абу
        abu_kickback = round(total_cost * 0.50, 2)
        await add_to_abu_fund(db, abu_kickback, donor_id=user_id, reason="bribe_cop_kickback")
        await record_user_transaction(
            db, user_id, -total_cost, "bribe_cop", f"Дача взятки следователю: -{stars_to_clear}★ (осталось {max(0, stars - stars_to_clear)}★)"
        )

    new_stars = max(0, stars - stars_to_clear)
    curr_bounty = profile["bounty_pool"]
    new_bounty = 0.0 if new_stars == 0 else max(0.0, round(curr_bounty - (BOUNTY_PER_STAR * stars_to_clear), 2))

    user_items["wanted_stars"] = new_stars
    user_items["bounty_pool"] = new_bounty
    user_items["bounty"] = new_bounty

    # Кросс-бордовая атомарная синхронизация по всем строкам Users
    await sync_user_criminal_status(db, user_id, user_items)
    await save_user_active_items(db, user_id, board_id, user_items)

    bank_unlock_text = ""
    if stars >= 5 and new_stars < 5:
        bank_unlock_text = (
            "\n\n🔓 <b>БАНКОВСКИЕ СЧЕТА И ПЕРЕВОДЫ РАЗБЛОКИРОВАНЫ!</b>\n"
            "Служба финансового мониторинга Абу сняла арест с твоих активов. "
            "Банковские операции (<code>/deposit</code>, <code>/withdraw</code>) и переводы (<code>/pay</code>) снова доступны!"
        )

    status_text = (
        "🕊️ <b>ТЫ ПОЛНОСТЬЮ ЧИСТ ПЕРЕД ЗАКОНОМ (0★)!</b>"
        if new_stars == 0 else
        f"⭐ Розыск снижен на <b>{stars_to_clear}★</b> (Текущий уровень: <b>{new_stars}★</b>)"
    )

    header = "✉️ <b>СЛЕДОВАТЕЛЬ ПРИНЯЛ КОНВЕРТ!</b>" if payment_method == "bribe_envelope" else "✉️ <b>СЛЕДОВАТЕЛЬ ПРИНЯЛ ВЗЯТКУ!</b>"
    success_msg = (
        f"{header}\n"
        f"{fluff}\n\n"
        f"{status_text}\n"
        f"💰 Баунти за твою голову: <code>{new_bounty:,.2f} ₪</code>\n"
        f"{payment_info}"
        f"{bank_unlock_text}"
    )

    return True, success_msg, {
        "new_stars": new_stars,
        "new_bounty": new_bounty,
        "cost_paid": cost_paid,
        "payment_method": payment_method,
        "envelopes_left": user_items.get("bribe_envelope", 0),
        "bank_unlocked": (stars >= 5 and new_stars < 5),
    }


@criminal_router.message(
    Command(
        "bribe_cop",
        "взятка_копу",
        "взятка_следователю",
        "взятка_следаку",
        "откупиться",
        "bribe_detective",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_bribe_cop(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /bribe_cop [all/все].
    Сбрасывает 1 звезду розыска или весь розыск целиком при указании 'all'.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    raw_text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    parts = raw_text.strip().split()
    clear_all = len(parts) >= 2 and parts[1].lower() in ("all", "все", "всё", "полностью", "clear")

    from common.db_pool import get_pool
    db = await get_pool()

    _, reply_text, _ = await execute_bribe_cop(db, user_id, board_id, clear_all=clear_all)
    await message.answer(reply_text, parse_mode="HTML")


async def format_wanted_board(db: Any) -> str:
    """
    Форматирует доску розыска Топ-10 преступников с гарантированным лимитом длины (<1500 символов).
    """
    async with db.execute("SELECT user_id, active_items FROM Users WHERE active_items LIKE '%\"wanted_stars\":%'") as cur:
        rows = await cur.fetchall()

    wanted_map: Dict[int, Tuple[int, float]] = {}
    for uid, a_str in rows:
        try:
            data = json.loads(a_str) if a_str else {}
            stars = int(data.get("wanted_stars", 0) or 0)
            bounty = float(data.get("bounty_pool", 0.0) or data.get("bounty", 0.0) or (stars * 5000.0))
            if stars > 0:
                if uid not in wanted_map or stars > wanted_map[uid][0] or (stars == wanted_map[uid][0] and bounty > wanted_map[uid][1]):
                    wanted_map[uid] = (stars, bounty)
        except Exception:
            pass

    if not wanted_map:
        return (
            "🕊️ <b>КРИМИНАЛЬНЫЙ МИР СПИТ:</b>\n"
            "На борде нет активных преступников в розыске. Все сычи законопослушны!"
        )

    sorted_criminals = sorted(wanted_map.items(), key=lambda x: (x[1][0], x[1][1]), reverse=True)
    top_list = sorted_criminals[:10]  # Строгое ограничение Топ-10

    lines = [
        "🚨 <b>ДОСКА ОРИЕНТИРОВОК ДРУЖИНЫ / РОЗЫСК (WANTED)</b>\n",
        f"Всего в федеральном розыске: <b>{len(sorted_criminals)}</b> беглецов.\n",
    ]
    for idx, (c_id, (stars, bounty)) in enumerate(top_list, 1):
        tag = format_anon_id(c_id)
        star_icons = "⭐️" * stars
        lines.append(f"<b>{idx}.</b> [<code>{tag}</code>] — {star_icons} <b>{stars}★</b> (<code>{bounty:,.0f} ₪</code>)")

    lines.append("\n👮 <i>Для ареста ответьте командой <code>/arrest</code> на пост преступника.</i>")
    lines.append("✉️ <i>Сбросить розыск без отсидки: <code>/bribe_cop</code>.</i>")

    result = "\n".join(lines)
    if len(result) > 1490:
        result = result[:1480] + "\n..."
    return result


@criminal_router.message(
    Command(
        "wanted",
        "bounty",
        "розыск",
        "ориентировки",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_wanted(message: types.Message, board_id: Optional[str] = None):
    """
    Доска ориентировок дружины: топ разыскиваемых преступников (строго Топ-10, <1500 символов).
    """
    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()

    text = await format_wanted_board(db)
    await message.answer(text, parse_mode="HTML")


async def format_jail_board(db: Any, caller_id: Optional[int] = None) -> str:
    """
    Форматирует статус КПЗ и список текущих арестантов (строго Топ-10, <1500 символов).
    """
    now_ts = time.time()
    caller_jail = None
    if caller_id:
        async with db.execute(
            "SELECT expires_at, reason FROM Mutes WHERE user_id = ? AND expires_at > ? LIMIT 1",
            (caller_id, now_ts),
        ) as cur:
            caller_jail = await cur.fetchone()

    async with db.execute(
        "SELECT user_id, expires_at, reason FROM Mutes WHERE expires_at > ? ORDER BY expires_at DESC LIMIT 10",
        (now_ts,),
    ) as cur:
        inmates = await cur.fetchall()

    lines = ["🔒 <b>ОБЕЗЬЯННИК И КПЗ /b/ (JAIL STATUS)</b>\n"]

    if caller_jail:
        rem_m = int(max(1, (caller_jail[0] - now_ts) // 60))
        reason = caller_jail[1] or "Без статьи"
        lines.append("⚠️ <b>ТЫ НАХОДИШЬСЯ ПОД АРЕСТОМ!</b>")
        lines.append(f"⏳ Срок: <b>{rem_m} мин.</b> | Статья: <i>{reason[:40]}</i>")
        lines.append("🕊️ Досрочный размут: <code>/bribe</code> (индульгенция).\n")

    if not inmates:
        lines.append("🕊️ <b>В камерах пусто!</b> На борде царит покой и порядок.")
    else:
        lines.append(f"👥 <b>Текущие арестанты в камерах (Топ-{len(inmates)}):</b>")
        for idx, (i_id, exp_at, r_text) in enumerate(inmates, 1):
            i_tag = format_anon_id(i_id)
            rem_m = int(max(1, (exp_at - now_ts) // 60))
            clean_reason = (r_text or "Без статьи")[:30]
            lines.append(f"<b>{idx}.</b> [<code>{i_tag}</code>] — <b>{rem_m} мин.</b> (<i>{clean_reason}</i>)")

    lines.append("\n👮 <i>Посадить преступника в КПЗ: <code>/arrest</code> [Reply].</i>")
    result = "\n".join(lines)
    if len(result) > 1490:
        result = result[:1480] + "\n..."
    return result


@criminal_router.message(
    Command(
        "jail",
        "кпз",
        "тюрьма",
        "изолятор",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_jail(message: types.Message, board_id: Optional[str] = None):
    """
    Статус КПЗ и список текущих арестантов (строго Топ-10, <1500 символов).
    """
    caller_id = message.from_user.id if message.from_user else 0

    from common.db_pool import get_pool
    db = await get_pool()

    text = await format_jail_board(db, caller_id)
    await message.answer(text, parse_mode="HTML")


async def execute_chloroform(
    db: Any,
    thief_id: int,
    victim_id: int,
    board_id: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Consumes 1 chloroform to put target to sleep for 30 minutes, disabling their pepperspray.
    """
    now = time.time()
    thief_tag = format_anon_id(thief_id)
    victim_tag = format_anon_id(victim_id)

    thief_items = await load_user_active_items(db, thief_id, board_id)
    chlor_count = int(thief_items.get("chloroform", 0) or 0)
    if chlor_count < 1:
        msg = (
            "🧪 <b>НЕТ ХЛОРОФОРМА!</b>\n"
            "У тебя нет хлороформа! Купи флакон на подпольном Даркнете: <code>/darknet</code>."
        )
        return False, msg, {"no_chloroform": True}

    if thief_id == victim_id:
        return False, "🤡 <b>ТЫ ЕБАНУЛСЯ?</b> Решил сам себе подышать хлороформом? Ответь реплаем на пост жертвы!", {}

    victim_items = await load_user_active_items(db, victim_id, board_id)
    thief_items["chloroform"] = chlor_count - 1

    sleep_duration = 1800.0  # 30 minutes
    victim_items["chloroformed_until"] = now + sleep_duration

    await save_user_active_items(db, thief_id, board_id, thief_items)
    await save_user_active_items(db, victim_id, board_id, victim_items)

    from common.database import record_user_transaction
    await record_user_transaction(
        db, thief_id, 0.0, "chloroform_use", f"Применение хлороформа на анона {victim_id}"
    )

    msg = (
        f"🧪 <b>ХЛОРОФОРМ ПРИМЕНЁН!</b>\n"
        f"Анон [<code>{thief_tag}</code>] подкрался сзади и прижал смоченную хлороформом тряпку к лицу анона [<code>{victim_tag}</code>]!\n\n"
        f"💤 Жертва крепко спит и пускает слюни на <b>30 минут</b>!\n"
        f"🧯 Перцовый баллончик цели полностью отключен и не сработает!\n"
        f"🧪 Осталось флаконов хлороформа: <b>{thief_items['chloroform']}</b>"
    )
    return True, msg, {
        "chloroformed_until": victim_items["chloroformed_until"],
        "duration": sleep_duration,
        "chloroform_left": thief_items["chloroform"],
    }


@criminal_router.message(
    Command(
        "chloroform",
        "хлороформ",
        "усыпить",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_chloroform(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /chloroform (reply to victim).
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    target_id = await safe_resolve_target(message)
    if not target_id:
        await message.answer(
            "🧪 <b>КОГО УСЫПЛЯТЬ-ТО?</b>\n"
            "Ответь <b>реплаем</b> на сообщение жертвы в треде, чтобы усыпить её хлороформом!",
            parse_mode="HTML",
        )
        return

    from common.db_pool import get_pool
    db = await get_pool()

    _, reply_text, _ = await execute_chloroform(db, user_id, target_id, board_id)
    await message.answer(reply_text, parse_mode="HTML")


@criminal_router.message(
    Command(
        "fake_passport",
        "паспорт",
        "поддельный_паспорт",
        "смена_паспорта",
        "липовый_паспорт",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_fake_passport(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /fake_passport:
    Использует поддельный паспорт из инвентаря для аннулирования федерального розыска.
    Если паспорта нет — предлагает приобрести его на Даркнете.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()

    items = await load_user_active_items(db, user_id, board_id)
    pass_cnt = int(items.get("fake_passport", 0) or 0)
    stars = int(items.get("wanted_stars", 0) or 0)

    if pass_cnt >= 1:
        items["fake_passport"] = pass_cnt - 1
        clear_wanted_status(items)
        await sync_user_criminal_status(db, user_id, items)
        await save_user_active_items(db, user_id, board_id, items)
        await message.answer(
            "🪪 <b>ПОДДЕЛЬНЫЙ ПАСПОРТ АКТИВИРОВАН!</b>\n\n"
            "Твоя личность в ориентировках МВД полностью изменена.\n"
            "Все звёзды розыска сброшены (0★), уголовное преследование прекращено!\n"
            "🔓 <b>Банковские счета и переводы разблокированы.</b>\n"
            f"<i>(Осталось паспортов в инвентаре: {items['fake_passport']} шт.)</i>",
            parse_mode="HTML"
        )
        return

    # Паспорта нет в инвентаре: пробуем купить на Даркнете
    ok, reply_text, _ = await handle_darknet_item_buy(db, user_id, board_id, "fake_passport")
    await message.answer(reply_text, parse_mode="HTML")


@criminal_router.message(
    Command(
        "lawyer",
        "advokat",
        "адвокат",
        "юрист",
        "защитник",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_lawyer(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /lawyer:
    Вызывает адвоката для апелляции следствия (-3★ розыска) и аннулирования ареста в КПЗ.
    Если адвокат не нанят — пытается нанять через Даркнет.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()

    items = await load_user_active_items(db, user_id, board_id)
    lawyer_cnt = int(items.get("lawyer", 0) or 0)
    stars = int(items.get("wanted_stars", 0) or 0)

    if lawyer_cnt >= 1:
        items["lawyer"] = lawyer_cnt - 1
        stars_dropped = min(3, stars)
        new_stars = max(0, stars - stars_dropped)
        curr_bounty = float(items.get("bounty_pool") or 0.0)
        new_bounty = max(0.0, round(curr_bounty * (new_stars / stars), 2)) if stars > 0 and new_stars > 0 else 0.0
        items["wanted_stars"] = new_stars
        items["bounty_pool"] = new_bounty
        items["bounty"] = new_bounty
        await sync_user_criminal_status(db, user_id, items)
        await save_user_active_items(db, user_id, board_id, items)

        # Снимаем арест в Mutes, если был
        try:
            await db.execute("DELETE FROM Mutes WHERE user_id = ? AND reason LIKE '%Арест%'", (user_id,))
            if hasattr(db, "commit"):
                await db.commit()
        except Exception:
            pass

        unlock_msg = "\n🔓 <b>Банковские счета и переводы разблокированы!</b>" if (stars >= 5 and new_stars < 5) else ""
        await message.answer(
            f"⚖️ <b>АДВОКАТ ВСТУПИЛ В ДЕЛО!</b>\n\n"
            f"Адвокат подал жалобу в прокуратуру на нарушения следователя.\n"
            f"Розыск снижен на <b>-{stars_dropped}★</b> (текущий уровень: <b>{new_stars}★</b>)!\n"
            f"Арест в КПЗ аннулирован.{unlock_msg}\n"
            f"<i>(Осталось услуг адвоката: {items['lawyer']} шт.)</i>",
            parse_mode="HTML"
        )
        return

    # Адвоката нет: пытаемся нанять в Даркнете
    ok, reply_text, _ = await handle_darknet_item_buy(db, user_id, board_id, "lawyer")
    await message.answer(reply_text, parse_mode="HTML")


@criminal_router.message(
    Command(
        "surrender",
        "сдаться",
        "чистосердечное",
        "повинная",
        ignore_case=True,
        ignore_mention=True,
    )
)
async def cmd_surrender(message: types.Message, board_id: Optional[str] = None):
    """
    Handler for /surrender:
    Добровольная сдача дружинникам: снимает статус розыска и отправляет в КПЗ
    на сокращенный срок отсидки (10 мин за звезду, макс 45 мин).
    """
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    if not board_id:
        board_id = getattr(message, "board_id", None) or "b"

    from common.db_pool import get_pool
    db = await get_pool()

    items = await load_user_active_items(db, user_id, board_id)
    stars = int(items.get("wanted_stars", 0) or 0)

    if stars <= 0:
        await message.answer("🕊️ <b>Вы чисты перед законом!</b> Сдаваться не в чем.", parse_mode="HTML")
        return

    jail_minutes = min(45, max(10, stars * 10))
    clear_wanted_status(items)
    await sync_user_criminal_status(db, user_id, items)
    await save_user_active_items(db, user_id, board_id, items)

    # Ставим мут ареста
    now = time.time()
    exp_ts = now + (jail_minutes * 60)
    try:
        await db.execute(
            """
            INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at, reason)
            VALUES (?, ?, 'arrest', ?, ?)
            """,
            (user_id, board_id, exp_ts, f"Арест дружинниками (явка с повинной, было {stars}★)")
        )
        if hasattr(db, "commit"):
            await db.commit()
    except Exception as e:
        logger.warning(f"Error setting surrender mute: {e}")

    await message.answer(
        f"🏛️ <b>ЯВКА С ПОВИННОЙ ОФОРМЛЕНА!</b>\n\n"
        f"Следователь принял чистосердечное признание. Все звёзды розыска аннулированы (0★)!\n"
        f"Срок отсидки в КПЗ: <b>{jail_minutes} минут</b>.\n"
        f"После отбытия срока ограничение будет автоматически снято, а счета разблокированы.",
        parse_mode="HTML"
    )
