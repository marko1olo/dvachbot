# invite_image_generator.py
"""
Graphic Invite Card Generator for Dvachbot (Тгач)
Generates stylized, high-impact invitation cards with random media, vector Tgach logo, QR codes,
12 distinct visual layout styles, and a massive collection of authentic Dvachean slogans.
"""

import os
import io
import sys
import json
import math
import random
import re
import asyncio
import sqlite3
import aiohttp
from typing import Optional, Tuple, Dict, List, Union, Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

try:
    import qrcode
except ImportError:
    qrcode = None

from common.config import DB_NAME

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(_BASE_DIR, "fonts")
IMPACT_FONT = os.path.join(FONTS_DIR, "Impact.ttf") if os.path.exists(os.path.join(FONTS_DIR, "Impact.ttf")) else None
MAIN_FONT = os.path.join(_BASE_DIR, "font1.ttf") if os.path.exists(os.path.join(_BASE_DIR, "font1.ttf")) else None
MONO_FONT = os.path.join(FONTS_DIR, "Courier New.ttf") if os.path.exists(os.path.join(FONTS_DIR, "Courier New.ttf")) else None
OCRA_FONT = os.path.join(FONTS_DIR, "ocra.ttf") if os.path.exists(os.path.join(FONTS_DIR, "ocra.ttf")) else None

# Massive collection of handcrafted on-image slogans (Badge + Headline + Subline)
IMAGE_SLOGANS = [
    {
        "badge": "АНАРХИЯ И АНОНИМНОСТЬ",
        "headline": "СЫЧ, ХВАТИТ ТЕРПЕТЬ!",
        "subline": "Залетай в Тгач — тут все свои дегенераты. Обсуждай что хочешь без цензуры и правил."
    },
    {
        "badge": "ДВАЧ • ТГАЧ /b/",
        "headline": "ТВОЁ МНЕНИЕ ЗДЕСЬ НАХУЙ НЕ НУЖНО",
        "subline": "Но высказать его можно безнаказанно. Заходи, обосри ОПа и получи дозу сажи."
    },
    {
        "badge": "1488% АНОНИМНОСТИ",
        "headline": "ЦИФРОВОЙ АД В ТВОЕМ КАРМАНЕ",
        "subline": "Без регистрации, СМС и морали. Товарищ майор плачет в сторонке."
    },
    {
        "badge": "ТОКСИЧНОСТЬ 1000%",
        "headline": "УСТАЛ ОТ ДУШНЫХ НОРМИСОВ?",
        "subline": "Смывайся в филиал /b/ прямо в телеге. Чистый контент, мемы и угар 24/7."
    },
    {
        "badge": "БАЗА ВЫДАНА",
        "headline": "ЕДИНСТВЕННЫЙ ЧАТ БЕЗ СОИ",
        "subline": "Шитпостинг высшей пробы, чернейший юмор и полная свобода слова."
    },
    {
        "badge": "ЛАМПОВЫЙ СЫЧ",
        "headline": "ТЫ НЕ ОДИН ТАКОЙ ЕБАНУТЫЙ",
        "subline": "Нас тут целый тред. Заваривай дошик, включай думерский плейлист и залетай."
    },
    {
        "badge": "БИТАРДЫ ОДОБРЯЮТ",
        "headline": "ОБНИМИ СВОЮ ШИЗУ",
        "subline": "В @dvach_chatbot твой внутренний голос наконец-то найдет единомышленников."
    },
    {
        "badge": "СВЕРХСЕКРЕТНО /b/",
        "headline": "ЗАБУДЬ ПРО РЕАЛЬНЫЙ МИР",
        "subline": "Твоя новая цифровая родина здесь. Сканируй QR или ищи в поиске."
    },
    {
        "badge": "ДВАЧЕВОРЕЗКА",
        "headline": "ХОЧЕШЬ ОБЩЕНИЯ, СКОТИНА?",
        "subline": "Тгач зовет: срачи, лампота, лоли, хентай и бесконечная деградация."
    },
    {
        "badge": "ПРИГЛАШЕНИЕ В АД",
        "headline": "ПОКА НОРМИСЫ СПЯТ",
        "subline": "Аноны деградируют. Присоединяйся к ночному дозору прямо сейчас."
    },
    {
        "badge": "ОСТОРОЖНО: МАТ",
        "headline": "ПОСЫЛАЕМ НАХУЙ С ЛЮБОВЬЮ",
        "subline": "Здесь нет банов за токсичность. Это не баг, это наша культура."
    },
    {
        "badge": "ПАЛАТА №6",
        "headline": "ПРИЕМ У ПСИХИАТРА ОТМЕНЯЕТСЯ",
        "subline": "Весь консилиум уже в треде. Заходи делиться своими галлюцинациями."
    },
    {
        "badge": "ОРУ В ГОЛОСИНУ",
        "headline": "КЕКНУТЬ С ПОДЛИВОЙ БЕСПЛАТНО",
        "subline": "Только отборный кринж и шедевры народной постиронии."
    },
    {
        "badge": "ДУМЕРСКИЙ РАЙ",
        "headline": "ЗА ОКОШКОМ ПАНЕЛЬКИ",
        "subline": "А в Тгаче тепло, лампово и наливают виртуальный спирт."
    },
    {
        "badge": "АБУ С НАМИ",
        "headline": "МИНУС МОЗГ, ПЛЮС АНОНИМНОСТЬ",
        "subline": "Вступай в орден святого двачевания. Сканируй QR-код."
    },
    {
        "badge": "РОДИНА ЖДЕТ",
        "headline": "ХВАТИТ ДРОЧИТЬ В ОДИНОЧКУ",
        "subline": "Обсуждай любимые тайтлы, вайфу и хентай в кругу ценителей."
    },
    {
        "badge": "ЧИСТАЯ АНАРХИЯ",
        "headline": "НИ БОГОВ, НИ ГОСПОД, ТОЛЬКО /B/",
        "subline": "Пиши что думаешь, никто не узнает твой IP и номер телефона."
    },
    {
        "badge": "ЭКСТРЕННЫЙ ВБРОС",
        "headline": "ПРОБИТИЕ ДНА ЗАФИКСИРОВАНО",
        "subline": "Твой персональный телепорт в эпицентр интернет-баталий."
    },
    {
        "badge": "GACHI APPROVED",
        "headline": "300 BUCKS И ТЫ В РАЮ",
        "subline": "Dungeon Master одобряет порку и вбросы на этой доске."
    },
    {
        "badge": "ОРДЕН БИТАРДОВ",
        "headline": "ОСТАВЬ НАДЕЖДУ, ВСЯК СЮДА ВХОДЯЩИЙ",
        "subline": "Вход бесплатный, выход платный (но выходить никто не хочет)."
    },
    {
        "badge": "КИБЕР-СЫЧЕВНЯ",
        "headline": "ЖИЗНЬ — ЭТО ИГРА С ПЛОХОЙ ГРАФИКОЙ",
        "subline": "А Тгач — это чит-код на веселье без цензуры."
    },
    {
        "badge": "ПРОВЕРКА НА ПРОЧНОСТЬ",
        "headline": "ВЫДЕРЖИТ ЛИ ТВОЙ ПЕРДАК?",
        "subline": "Самые горячие срачи рунета уже ждут тебя в комментариях."
    },
    {
        "badge": "ШИЗОФАЗИЯ ON",
        "headline": "ГОЛОСА В ГОЛОВЕ ПРАВЫ",
        "subline": "Они велят тебе отсканировать QR и залететь в наш анонимный чат."
    },
    {
        "badge": "БЕСКОНЕЧНЫЙ ТРЕД",
        "headline": "НОЧЬ, ДОШИРАК, ДВАЧ",
        "subline": "Идеальное комбо для спасения от экзистенциальной тоски."
    },
    {
        "badge": "СВЯТАЯ САЖА",
        "headline": "САЖА ВЕРШИТ ПРАВОСУДИЕ",
        "subline": "Опусти тупого ОПа на дно истории одним кликом."
    },
    {
        "badge": "ХЕНТАЙ-ПАТРУЛЬ",
        "headline": "КУЛЬТУРНЫЙ ОТДЫХ ДЛЯ ГОСПОД",
        "subline": "Лучшие арты, соусы и фан-арты без купюр и ханжества."
    },
    {
        "badge": "АНТИ-ЗУМЕР",
        "headline": "НИКАКИХ ТИКТОКОВ И КРИНЖА",
        "subline": "Старая школа интернет-террора и лампового общения."
    },
    {
        "badge": "МАТРИЦА СЛОМАЛАСЬ",
        "headline": "КРАСНАЯ ТАБЛЕТКА В ТВОИХ РУКАХ",
        "subline": "Прими правду и стань полноправным обитателем анонимной сети."
    },
    # Extended Authentic Slogans Collection (+20 new high-impact slogans)
    {
        "badge": "СВЯТАЯ КАПЧА",
        "headline": "ТЫ КТО ТАКОЙ? СУКА, ЗАХОДИ!",
        "subline": "В Тгаче нет регистрации и лиц. Только чистый поток сознания и твой крик души."
    },
    {
        "badge": "АГИТПРОП /b/",
        "headline": "ТОВАРИЩ СЫЧ, ТЫ В ТРЕДЕ?!",
        "subline": "Пятилетку деградации за три дня. Вступай в анонимную ударную бригаду Тгача."
    },
    {
        "badge": "БУГУРТ-ТРЕД",
        "headline": "БОМБИТ ТАК, ЧТО ВИДНО ИЗ КОСМОСА",
        "subline": "Выплесни всю желчь на доску. Здесь поймут, поддержат или добьют в комментариях."
    },
    {
        "badge": "ПЛАТИНОВЫЙ СОУС",
        "headline": "СОУС ЗАПИЛЕН, ОП НЕ ХУЙ",
        "subline": "Коллекция лучших тредов, артов и веб-архивов прямо в твоем кармане."
    },
    {
        "badge": "НОЧНОЙ ДОЗОР",
        "headline": "3 ЧАСА НОЧИ. ВРЕМЯ ШИЗЫ",
        "subline": "Когда нормальные люди спят, битарды строят теории заговора и делятся сокровенным."
    },
    {
        "badge": "АНАЛОГОВЫЙ КОШМАР",
        "headline": "ЭТОТ СИГНАЛ НЕЛЬЗЯ ЗАГЛУШИТЬ",
        "subline": "Вход в закрытую сеть свободного рунета. Сканируй код и принимай передачу."
    },
    {
        "badge": "ИНКВИЗИЦИЯ /b/",
        "headline": "ЕРЕСЬ ВЫСШЕЙ ПРОБЫ",
        "subline": "Оставь нормы приличия за порогом. В Тгаче нет запретных тем и догм."
    },
    {
        "badge": "ПАСТА-МАШИНА",
        "headline": "ТВОЙ БАТЯ ЗАШЁЛ В ТРЕД",
        "subline": "И принёс жареный суп со вкусом старого доброго двачевания без цензуры."
    },
    {
        "badge": "ПЕРЕКАТ В БЕЗДНУ",
        "headline": "СТАРЫЙ ТРЕД УТОНУЛ",
        "subline": "Новый уже на первой странице. Запрыгивай в вагон бесконечного шитпостинга."
    },
    {
        "badge": "БЕЗ РЕГИСТРАЦИИ",
        "headline": "НИКАКИХ ТЕЛЕФОНОВ И ПАСПОРТОВ",
        "subline": "Полная анонимность старой школы. Забудь про слежку и цифровой концлагерь."
    },
    {
        "badge": "СЫЧЕВАРНЯ 2.0",
        "headline": "ТЕПЛО, ЛАМПОВО И ПАХНЕТ ПЕЛЬМЕНЯМИ",
        "subline": "Лучшее убежище от внешнего мира. Уютный чат для тех, кто устал от людей."
    },
    {
        "badge": "КУЛЬТУРА ДЕГРАДАЦИИ",
        "headline": "УМНЫЕ РАЗГОВОРЫ ДЛЯ ГЛУПЫХ ЛЮДЕЙ",
        "subline": "От квантовой физики до любимых сортов доширака за 5 секунд."
    },
    {
        "badge": "БАЗИРОВАННЫЙ ТГАЧ",
        "headline": "СЛИШКОМ ЖЁСТКО ДЛЯ ТЕЛЕГРАМА",
        "subline": "Но мы всё равно здесь. Сканируй QR, пока РКН протирает свои мониторы."
    },
    {
        "badge": "АЛЁ, ЭТО ДВАЧ?",
        "headline": "ДА, ПОШЁЛ НАХУЙ",
        "subline": "Традиционное приветствие для новоприбывших. Заходи, будь как дома."
    },
    {
        "badge": "ЭРА ПОСТИРОНИИ",
        "headline": "МЫ ВСЁ ЕЩЁ РОФЛИМ ИЛИ УЖЕ НЕТ?",
        "subline": "Грань между шуткой и реальностью стёрта. Исследуй глубины постиронии вместе с нами."
    },
    {
        "badge": "БИТАРДЫ ВСЕХ СТРАН",
        "headline": "ОБЪЕДИНЯЙТЕСЬ В ТГАЧЕ!",
        "subline": "Самый масштабный анонимный синдикат рунета ждёт свежую кровь."
    },
    {
        "badge": "ХВАТИТ ДУМАТЬ",
        "headline": "ОТКЛЮЧИ МОЗГ, ВКЛЮЧИ /b/",
        "subline": "Прямой впрыск чистого контента без фильтров и модераторского произвола."
    },
    {
        "badge": "АНТИ-СКУФ",
        "headline": "СПАСИ СЕБЯ ОТ ДИВАННОЙ РУТИНЫ",
        "subline": "Окунись в дикую анархию мемов, вбросов и ночных откровений."
    },
    {
        "badge": "ПАТРУЛЬ ДЕГРАДАЦИИ",
        "headline": "САЖА ВМЕСТО ЛАЙКОВ",
        "subline": "Здесь не дрочат на социальный рейтинг. Пиши что думаешь и лови фидбек."
    },
    {
        "badge": "ЦИФРОВОЙ КАТАРСИС",
        "headline": "ВСЁ ТЛЕН, КРОМЕ /b/",
        "subline": "Очисти свой разум от информационного мусора в ламповом анонимном котле."
    }
]

# Accompanying unique companion texts for auto-posts
AUTO_POST_COMPANION_TEXTS = [
    (
        "🔥 <b>Сводка из глубин Тгача:</b>\n\n"
        "Анон, пока нормисы обсуждают погоду в офисных чатах, у нас кипят эпичные срачи, "
        "рождаются легендарные пасты и льется отборная сажа. Не будь чужим на этом празднике деградации!\n\n"
        "👉 <i>Сохраняй карточку, кидай друзьям в конфу или сканируй QR-код:</i>"
    ),
    (
        "💀 <b>Экстренное включение /b/:</b>\n\n"
        "Устал от банов за слово «пидор» и цензуры в обычных каналах? Тгач — это последний оплот "
        "абсолютной анонимности. Пиши любую шизу, сливай секреты, спорь до хрипоты.\n\n"
        "👉 <i>Перешли инвайт знакомому сычу — спаси его от соевого интернета:</i>"
    ),
    (
        "🌸 <b>Ночной тред ждет тебя:</b>\n\n"
        "Одиноко, темно и хочется поговорить по душам (или кого-нибудь покрыть хуями)? "
        "Вливайся в наш анонимный котел. Тут тебя поймут, обнимут или обосрут — в зависимости от настроения.\n\n"
        "👉 <i>Твой персональный инвайт-билет:</i>"
    ),
    (
        "⚡ <b>Портал в двачевское подполье:</b>\n\n"
        "Без регистрации, без телефонных номеров, без лицемерия. Настоящий дух нулевых "
        "прямо в мессенджере. Сканируй код на картинке и заходи на доску.\n\n"
        "👉 <i>Делись с бро и залетай:</i>"
    ),
    (
        "🧠 <b>Шизо-проповедь дня:</b>\n\n"
        "Если ты чувствуешь, что вокруг матрица и все сошли с ума — добро пожаловать домой. "
        "В Тгаче все давно признали свой диагноз и весело проводят время.\n\n"
        "👉 <i>Лови инвайт-карточку с QR-кодом:</i>"
    ),
    (
        "🍻 <b>Вечерний сбор битардов:</b>\n\n"
        "Заваривай чай/пивас и заходи на перекличку. В тредах уже делят мир, обсуждают теории заговора "
        "и постят годноту. Не пропусти главное!\n\n"
        "👉 <i>Отсканируй или перешли друзьям:</i>"
    ),
    (
        "🚀 <b>Рейд в реальность отменяется:</b>\n\n"
        "Зачем выходить на улицу, когда в @dvach_chatbot есть всё: политика, хентай, мемы, "
        "философия и бесплатный душевный покой без цензуры.\n\n"
        "👉 <i>Залетай на доску:</i>"
    ),
    (
        "🪆 <b>Майор в замешательстве:</b>\n\n"
        "Никаких логов, никакой привязки к аккаунтам, чистый двачевский протокол. "
        "Забирай инвайт-постер и приглашай всех, кто устал от корпоративного интернета.\n\n"
        "👉 <i>Твой QR-ключ от Тгача:</i>"
    ),
    (
        "🎭 <b>Театр абсурда открывает двери:</b>\n\n"
        "Здесь каждый анон — либо философ, либо клоун, либо тролль 80 уровня. "
        "Вступай в дискуссии, байти школьников и делись своими сокровенными мыслями.\n\n"
        "👉 <i>Сканируй карточку:</i>"
    ),
    (
        "⚡ <b>Прямой эфир с передовой шитпостинга:</b>\n\n"
        "Никаких алгоритмических лент и рекламы крипто-каналов. Живой поток мыслей "
        "от тысяч анонимных пользователей в реальном времени.\n\n"
        "👉 <i>Кидай бро и залетай:</i>"
    ),
    # New Companion Texts
    (
        "📯 <b>Декрет Революционного Военсовета /b/:</b>\n\n"
        "Товарищ сыч! Пока алгоритмы впаривают тебе рекламу курсов и соевый контент, "
        "анонимный авангард Тгача куёт свободу слова без купюр. Пятилетку угара выполняем досрочно!\n\n"
        "👉 <i>Печатай инвайт, передавай товарищам или сканируй QR-код:</i>"
    ),
    (
        "📼 <b>Перехват засекреченной частоты:</b>\n\n"
        "Внимание: обнаружен немодерируемый сигнал с борды. Никаких телефонных привязок, никаких "
        "историй переписок для товарища майора. Полное погружение в атмосферу дикого раннего веба.\n\n"
        "👉 <i>Ключ дешифровки на карточке:</i>"
    ),
    (
        "🕯 <b>Тайный орден анонимных еретиков:</b>\n\n"
        "Устал от ханжества и навязанных правил? В обители Тгача каждый волен сбросить маску нормальности. "
        "Здесь спорят до победного, делятся запретными мыслями и не боятся обидеть нежные чувства.\n\n"
        "👉 <i>Свиток с печатью для входа:</i>"
    ),
    (
        "💥 <b>Срочный бугурт-патруль:</b>\n\n"
        "Чувствуешь, как закипает котёл от ежедневной рутины? Не держи в себе — неси на доску. "
        "В комментариях всегда найдётся десяток анонов, готовых подлить масла в огонь или поддержать словом.\n\n"
        "👉 <i>Залетай на огонёк:</i>"
    ),
    (
        "🍜 <b>Сычевальня выходит на связь:</b>\n\n"
        "Ночь, монитор тускло светит в темноте, чай уже остыл... Самое время открыть Тгач. "
        "Ламповые треды с историями из жизни, обсуждения любимых тайтлов и тёплая атмосфера сычевания.\n\n"
        "👉 <i>Твой билет в сычевню:</i>"
    ),
    (
        "🦾 <b>Индустриальный протокол Тгача:</b>\n\n"
        "Ноль рекламы. Ноль цензуры. Ноль лицемерия. Только чистый контент, ядовитый юмор "
        "и полная свобода самовыражения. Вступай в крупнейшую анонимную сеть телеграма прямо сейчас.\n\n"
        "👉 <i>Сканируй QR и присоединяйся:</i>"
    )
]

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE
)

_UNSUPPORTED_GLYPH_REPLACEMENTS = {
    "★": "*",
    "☆": "*",
    "⚡": "[!]",
    "▶": ">",
    "◀": "<",
    "▲": "^",
    "▼": "v",
    "✠": "+",
    "✦": "*",
    "◆": "*",
    "●": "*",
    "■": "#",
    "▪": "-",
    "▫": "-",
}

def clean_text_for_font(text: str) -> str:
    """Removes unsupported emoji glyphs and normalizes symbols for clean TTF rendering."""
    if not text:
        return ""
    cleaned = text
    for sym, rep in _UNSUPPORTED_GLYPH_REPLACEMENTS.items():
        cleaned = cleaned.replace(sym, rep)
    cleaned = EMOJI_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def fit_and_crop(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Resizes and center-crops image to target dimensions without squashing or distortion."""
    w, h = img.size
    if w == target_width and h == target_height:
        return img
    scale = max(target_width / w, target_height / h)
    nw, nh = int(math.ceil(w * scale)), int(math.ceil(h * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - target_width) // 2
    top = (nh - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))

def draw_tgach_logo(size: int = 56, bg_color: Tuple[int, int, int, int] = (0, 136, 204, 255)) -> Image.Image:
    """
    Renders the official vector Tgach logo:
    Electric Telegram Blue rounded square with a pure white lightning bolt inside.
    """
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    r = int(s * 0.22)
    draw.rounded_rectangle([0, 0, s, s], radius=r, fill=bg_color)
    draw.rounded_rectangle([scale, scale, s - scale, s - scale], radius=r - scale, outline=(255, 255, 255, 220), width=int(2 * scale))
    
    poly_norm = [
        (0.56, 0.15),
        (0.28, 0.50),
        (0.48, 0.50),
        (0.40, 0.85),
        (0.72, 0.44),
        (0.52, 0.44),
    ]
    poly = [(int(x * s), int(y * s)) for x, y in poly_norm]
    shadow_poly = [(x + int(2.5 * scale), y + int(2.5 * scale)) for x, y in poly]
    
    draw.polygon(shadow_poly, fill=(0, 45, 80, 180))
    draw.polygon(poly, fill=(255, 255, 255, 255))
    
    return img.resize((size, size), Image.Resampling.LANCZOS)

def draw_wax_seal(size: int = 64) -> Image.Image:
    """Renders a crimson wax seal with embossed border and golden Tgach lightning bolt."""
    scale = 3
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    cx, cy = s // 2, s // 2
    r = s // 2 - 4 * scale
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(145, 18, 26, 255), outline=(100, 10, 16, 255), width=3 * scale)
    inner_r = r - 7 * scale
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], outline=(190, 45, 55, 220), width=2 * scale)
    
    poly_norm = [
        (0.56, 0.16),
        (0.30, 0.50),
        (0.48, 0.50),
        (0.40, 0.84),
        (0.70, 0.44),
        (0.52, 0.44),
    ]
    poly = [(int(x * s), int(y * s)) for x, y in poly_norm]
    shadow_poly = [(x + 2*scale, y + 2*scale) for x, y in poly]
    draw.polygon(shadow_poly, fill=(60, 5, 8, 200))
    draw.polygon(poly, fill=(245, 195, 50, 255))
    
    return img.resize((size, size), Image.Resampling.LANCZOS)

def create_procedural_background(width: int = 800, height: int = 800, style: int = 0) -> Image.Image:
    """Generates an atmospheric procedural Dvach image with noise, grid and crisp watermark."""
    img = Image.new("RGB", (width, height), (14, 14, 20))
    draw = ImageDraw.Draw(img)
    
    for y in range(height):
        ratio = y / height
        if style == 1:
            r = int(16 + ratio * 38)
            g = int(12 + ratio * 18)
            b = int(28 + ratio * 58)
        else:
            r = int(24 + ratio * 38)
            g = int(18 + (1.0 - ratio) * 16)
            b = int(28 + ratio * 32)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
        
    grid_step = 40
    for x in range(0, width, grid_step):
        draw.line([(x, 0), (x, height)], fill=(36, 40, 54), width=1)
    for y in range(0, height, grid_step):
        draw.line([(0, y), (width, y)], fill=(36, 40, 54), width=1)
        
    # Layer 1: Atmospheric glow (blurred)
    glow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_overlay)
    glow_color = (255, 130, 0, 40) if style == 0 else (160, 40, 240, 40)
    glow_draw.ellipse([width//4, height//4, 3*width//4, 3*height//4], fill=glow_color)
    glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(radius=32))
    img = Image.alpha_composite(img.convert("RGBA"), glow_overlay)
    
    # Layer 2: Sharp semi-transparent "2ch" watermark text
    wm_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm_overlay)
    wm_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 190)
    wm_text = "2ch"
    wm_bbox = wm_draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    wm_h = wm_bbox[3] - wm_bbox[1]
    wm_x = (width - wm_w) // 2
    wm_y = (height - wm_h) // 2 - 20
    wm_draw.text((wm_x, wm_y), wm_text, font=wm_font, fill=(255, 140, 0, 32))
    
    img = Image.alpha_composite(img, wm_overlay).convert("RGB")
    return img

def generate_qr(target_url: str, box_size: int = 4, border: int = 1, fill_color: str = "#ff8800", back_color: str = "#0e0e14") -> Image.Image:
    """Generates a customizable high-contrast QR code with graceful fallback."""
    if qrcode is not None:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=box_size,
                border=border,
            )
            qr.add_data(target_url)
            qr.make(fit=True)
            return qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGBA")
        except Exception:
            pass
    # Fallback placeholder if qrcode is missing or fails
    size = max(60, box_size * 29 + border * 2)
    fallback = Image.new("RGBA", (size, size), back_color)
    fdraw = ImageDraw.Draw(fallback)
    fdraw.rectangle([border, border, size - border - 1, size - border - 1], outline=fill_color, width=2)
    fdraw.text((size // 2 - 22, size // 2 - 6), "TGACH", fill=fill_color)
    return fallback

def _decode_and_verify_image(data_bytes: bytes) -> Optional[Image.Image]:
    try:
        buf = io.BytesIO(data_bytes)
        img = Image.open(buf)
        img.verify()
        buf.seek(0)
        img_rgb = Image.open(buf).convert("RGB")
        img_rgb.load()
        return img_rgb
    except Exception:
        return None

def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Wraps text within a given pixel width."""
    lines = []
    words = text.split()
    if not words:
        return lines
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
    if current_line:
        lines.append(" ".join(current_line))
    return lines

async def fetch_random_post_image(board_id: str = "b", bot: Optional[Any] = None) -> Optional[Image.Image]:
    """Fetches a random photo from the database for the given board.
    First tries to download via Telegram Bot API using file_id.
    If that fails or no bot, falls back to direct URL fetch.
    Returns a PIL Image object or None.
    """
    db_path = os.fspath(DB_NAME)
    if not os.path.exists(db_path):
        return None

    candidates = []
    file_id_candidates = []

    # 1. Try canonical get_random_image_post from common.database
    try:
        from common.database import get_random_image_post
        target_boards = [board_id] if board_id else ['b', 'thread']
        post = await get_random_image_post(allowed_boards=target_boards)
        if post and isinstance(post, dict) and 'content' in post:
            files = post['content'].get('files', [])
            idx = post.get('_selected_file_index', 0)
            if idx < len(files):
                f = files[idx]
                fid = f.get('original_file_id') or f.get('file_id') or f.get('thumbnail_file_id')
                url = f.get('original_url') or f.get('thumbnail_url')
                if fid: file_id_candidates.append(fid)
                if url: candidates.append(url)
    except Exception:
        pass

    # 2. Try FileRegistry
    try:
        from common.db_pool import get_pool
        db = await get_pool()
        if db and getattr(db, '_running', False):
            async with db.execute("""
                SELECT file_id, thumbnail_id FROM FileRegistry 
                WHERE file_type = 'photo' AND (file_id IS NOT NULL OR thumbnail_id IS NOT NULL)
                ORDER BY RANDOM() LIMIT 20
            """) as cursor:
                async for fid, thumb_id in cursor:
                    target_fid = fid or thumb_id
                    if target_fid:
                        file_id_candidates.append(target_fid)
    except Exception:
        pass

    # Try downloading real user photo via Bot API if bot instance is available
    if bot and file_id_candidates:
        random.shuffle(file_id_candidates)
        for fid in file_id_candidates[:8]:
            try:
                buf = io.BytesIO()
                file_info = await bot.get_file(fid)
                if not file_info or not file_info.file_path:
                    continue
                await bot.download_file(file_info.file_path, destination=buf)
                raw_bytes = buf.getvalue()
                if len(raw_bytes) > 4000:
                    decoded = await asyncio.to_thread(_decode_and_verify_image, raw_bytes)
                    if decoded is not None:
                        return decoded
            except Exception:
                continue

    # Try HTTP URLs from DB (parallel fast fetch)
    if candidates:
        random.shuffle(candidates)
        timeout = aiohttp.ClientTimeout(total=2.0)
        async def _fetch_one(session, url):
            try:
                async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 4000:
                            return await asyncio.to_thread(_decode_and_verify_image, data)
            except Exception:
                pass
            return None

        try:
            async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(ssl=False), connector_owner=True) as session:
                tasks = [_fetch_one(session, u) for u in candidates[:5]]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Image.Image):
                        return r
        except Exception:
            pass

    return None

# ==========================================
# 12 DISTINCT VISUAL LAYOUT RENDERERS
# ==========================================

def _render_layout_cyber_board(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 0: Classic Cyber Imageboard Noir with Top Logo + Orange Badges + Bottom QR."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    for y in range(130):
        alpha = int(230 * (1.0 - y / 130))
        ov_draw.line([(0, y), (target_width, y)], fill=(8, 8, 14, alpha))
        
    for y in range(target_height - 360, target_height):
        ratio = (y - (target_height - 360)) / 360
        alpha = int(248 * (ratio ** 1.2))
        ov_draw.line([(0, y), (target_width, y)], fill=(6, 6, 12, alpha))
        
    logo_size = 48
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (22, 18), logo_resized)
    
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20)
    header_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 28)
    
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "ДВАЧ • ТГАЧ"))
    badge_bbox = ov_draw.textbbox((0, 0), badge_clean, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 20
    
    ov_draw.rounded_rectangle([78, 20, 78 + badge_w, 56], radius=6, fill=(255, 136, 0, 240))
    ov_draw.text((88, 25), badge_clean, font=badge_font, fill=(0, 0, 0, 255))
    
    b_label = f"/{board_id}/" if board_id else "/b/"
    ov_draw.text((88 + badge_w + 12, 23), f"{b_label} {bot_username}", font=header_font, fill=(255, 255, 255, 255))
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ЗАХОДИ В ТГАЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Анонимный чат прямо в телеграме."))
    
    max_text_w = target_width - 240
    hl_font_size = 36
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font_size = 22
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    while len(sub_lines) > 3 and sub_font_size > 16:
        sub_font_size -= 2
        sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
        sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
        
    total_block_h = (len(hl_lines) * (hl_font_size + 6)) + 12 + (len(sub_lines) * (sub_font_size + 6))
    start_y = target_height - 50 - total_block_h - 20
    
    curr_y = start_y
    for line in hl_lines:
        for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4), (0, -3)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=hl_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=hl_font, fill=(255, 185, 45, 255))
        curr_y += hl_font_size + 6
        
    curr_y += 10
    for line in sub_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=sub_font, fill=(240, 240, 245, 255))
        curr_y += sub_font_size + 6
        
    footer_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, 15)
    ov_draw.text((35, target_height - 35), ">> Сканируй QR-код или ищи в поиске: " + bot_username, font=footer_font, fill=(255, 160, 40, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1)
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 30
    qr_box_y = target_height - qr_h - 45
    
    ov_draw.rounded_rectangle([qr_box_x - 8, qr_box_y - 8, qr_box_x + qr_w + 8, qr_box_y + qr_h + 8], radius=8, fill=(14, 14, 20, 255), outline=(255, 140, 0, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 6, qr_box_y + qr_h + 10), "|| SCAN ME ||", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 14), fill=(255, 160, 0, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_demotivator(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 1: Classic 2ch Demotivator Poster Style with solid black border & crisp framing."""
    frame_img = Image.new("RGB", (target_width, target_height), (8, 8, 12))
    pad_x, pad_top = 40, 36
    inner_w = target_width - (pad_x * 2)
    inner_h = int(target_height * 0.62)
    
    cropped_base = fit_and_crop(base, inner_w, inner_h)
    frame_img.paste(cropped_base, (pad_x, pad_top))
    
    draw = ImageDraw.Draw(frame_img)
    draw.rectangle([pad_x - 4, pad_top - 4, pad_x + inner_w + 4, pad_top + inner_h + 4], outline=(255, 255, 255, 220), width=2)
    
    logo_size = 42
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    frame_img.paste(logo_resized, (pad_x + 12, pad_top + 12), logo_resized)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ЗАХОДИ В ТГАЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Анонимный чат прямо в телеграме."))
    
    hl_font_size = 36
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    max_w = target_width - 240
    hl_lines = wrap_text(headline_clean, hl_font, max_w, draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_w, draw)
        
    sub_font_size = 20
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_w, draw)
    
    start_y = pad_top + inner_h + 20
    curr_y = start_y
    for line in hl_lines:
        draw.text((45, curr_y), line, font=hl_font, fill=(255, 255, 255))
        curr_y += hl_font_size + 4
        
    curr_y += 6
    for line in sub_lines:
        draw.text((45, curr_y), line, font=sub_font, fill=(255, 180, 50))
        curr_y += sub_font_size + 4
        
    draw.text((45, target_height - 35), f">> /{board_id}/ • {bot_username}", font=ImageFont.truetype(MAIN_FONT, 15), fill=(0, 150, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1)
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 36
    qr_box_y = target_height - qr_h - 40
    
    draw.rounded_rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], radius=6, fill=(14, 14, 20), outline=(0, 136, 204), width=2)
    frame_img.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    draw.text((qr_box_x + 8, qr_box_y + qr_h + 8), "|| SCAN ||", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12), fill=(0, 180, 255))
    
    return frame_img

def _render_layout_cyber_plaque(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 2: Cyber Plaque with Glassmorphic bottom card, glowing electric blue line and QR."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    logo_size = 52
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (25, 22), logo_resized)
    
    ov_draw.text((88, 28), f"ТГАЧ /{board_id}/ • {bot_username}", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 28), fill=(255, 255, 255, 255))
    
    card_y = target_height - 290
    ov_draw.rounded_rectangle([20, card_y, target_width - 20, target_height - 20], radius=16, fill=(12, 14, 22, 235), outline=(0, 136, 204, 240), width=2)
    ov_draw.line([(28, card_y + 4), (target_width - 28, card_y + 4)], fill=(255, 140, 0, 220), width=2)
    
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "ТОПОВЫЙ ВБРОС"))
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ЗАХОДИ В ТГАЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Анонимный чат прямо в телеграме."))
    
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18)
    badge_bbox = ov_draw.textbbox((0, 0), badge_clean, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 20
    
    ov_draw.rounded_rectangle([40, card_y + 18, 40 + badge_w, card_y + 46], radius=4, fill=(0, 136, 204, 240))
    ov_draw.text((50, card_y + 22), badge_clean, font=badge_font, fill=(255, 255, 255, 255))
    
    max_text_w = target_width - 240
    hl_font_size = 32
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, 20)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    curr_y = card_y + 56
    for line in hl_lines:
        ov_draw.text((40, curr_y), line, font=hl_font, fill=(255, 185, 45, 255))
        curr_y += hl_font_size + 4
        
    curr_y += 4
    for line in sub_lines:
        ov_draw.text((40, curr_y), line, font=sub_font, fill=(240, 240, 245, 255))
        curr_y += 24
        
    ov_draw.text((40, target_height - 48), ">> Сканируй QR для входа на борду", font=ImageFont.truetype(MAIN_FONT, 15), fill=(0, 180, 255, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1)
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 45
    qr_box_y = card_y + 35
    
    ov_draw.rounded_rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], radius=6, fill=(10, 10, 16, 255), outline=(255, 140, 0, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 6, qr_box_y + qr_h + 8), "|| SCAN ME ||", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12), fill=(255, 160, 0, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_vapor_neon(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 3: Vaporwave / Cyber-Neon with Magenta & Cyan Glow, Glitch ribbons and high contrast."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    ov_draw.rectangle([0, 0, target_width, 68], fill=(16, 12, 28, 240))
    ov_draw.line([(0, 68), (target_width, 68)], fill=(255, 0, 128, 255), width=3)
    
    logo_size = 46
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (20, 11), logo_resized)
    
    ov_draw.text((78, 16), f"// TGACH /{board_id}/ • CYBER-BOARD //", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 26), fill=(0, 240, 255, 255))
    
    for y in range(target_height - 340, target_height):
        ratio = (y - (target_height - 340)) / 340
        alpha = int(245 * (ratio ** 1.1))
        ov_draw.line([(0, y), (target_width, y)], fill=(12, 8, 24, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ЗАХОДИ В ТГАЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Анонимный чат прямо в телеграме."))
    
    max_text_w = target_width - 240
    hl_font_size = 36
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font_size = 22
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 40 - (len(hl_lines)*(hl_font_size+6)) - (len(sub_lines)*(sub_font_size+6)) - 35
    curr_y = start_y
    for line in hl_lines:
        ov_draw.text((32, curr_y + 3), line, font=hl_font, fill=(255, 0, 128, 220))
        ov_draw.text((38, curr_y - 2), line, font=hl_font, fill=(0, 240, 255, 220))
        ov_draw.text((35, curr_y), line, font=hl_font, fill=(255, 255, 255, 255))
        curr_y += hl_font_size + 6
        
    curr_y += 8
    for line in sub_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=sub_font, fill=(0, 240, 255, 255))
        curr_y += sub_font_size + 6
        
    ov_draw.text((35, target_height - 35), ">> СКАНИРУЙ QR-КОД << " + bot_username, font=ImageFont.truetype(MAIN_FONT, 15), fill=(255, 0, 128, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#00f0ff", back_color="#0a0614")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 30
    qr_box_y = target_height - qr_h - 45
    
    ov_draw.rounded_rectangle([qr_box_x - 8, qr_box_y - 8, qr_box_x + qr_w + 8, qr_box_y + qr_h + 8], radius=8, fill=(10, 6, 18, 255), outline=(255, 0, 128, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 8, qr_box_y + qr_h + 10), ">> NEON QR <<", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12), fill=(0, 240, 255, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_breaking_news(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 4: Breaking News Alert Style with Red/Yellow Ticker Banner & Radar Frame."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    ov_draw.rectangle([0, 0, target_width, 60], fill=(204, 0, 0, 245))
    logo_size = 44
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (16, 8), logo_resized)
    
    ov_draw.text((70, 14), "[!] ЭКСТРЕННЫЙ ВЫПУСК /B/ • ТГАЧ NEWS", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 26), fill=(255, 255, 255, 255))
    
    ov_draw.rectangle([0, 60, target_width, 90], fill=(255, 204, 0, 245))
    ov_draw.text((20, 66), f"МАССОВЫЙ ВБРОС НА ДОСКЕ /{board_id}/ >> {bot_username} >> АНОНЫ В АХУЕ >>", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18), fill=(0, 0, 0, 255))
    
    for y in range(target_height - 300, target_height):
        ratio = (y - (target_height - 300)) / 300
        alpha = int(250 * (ratio ** 1.15))
        ov_draw.line([(0, y), (target_width, y)], fill=(8, 8, 12, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "СРОЧНО В НОМЕР!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Главные события анонимного рунета."))
    
    max_text_w = target_width - 240
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, 21)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 40 - (len(hl_lines)*38) - (len(sub_lines)*26) - 25
    curr_y = start_y
    for line in hl_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=hl_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=hl_font, fill=(255, 235, 60, 255))
        curr_y += 38
        
    curr_y += 6
    for line in sub_lines:
        ov_draw.text((35, curr_y), line, font=sub_font, fill=(255, 255, 255, 255))
        curr_y += 26
        
    ov_draw.text((35, target_height - 35), ">> ПРЯМОЙ ЭФИР ИЗ БЕЗДНЫ: " + bot_username, font=ImageFont.truetype(MAIN_FONT, 15), fill=(255, 80, 80, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#ffcc00", back_color="#121218")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 30
    qr_box_y = target_height - qr_h - 45
    
    ov_draw.rounded_rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], radius=6, fill=(12, 12, 18, 255), outline=(204, 0, 0, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 12, qr_box_y + qr_h + 8), "|| LIVE QR ||", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12), fill=(255, 204, 0, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_anime_japan(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 5: Japanese Anime Aesthetic with gold/cherry frame, dynamic badge & sakura pink QR."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # Outer gold/sakura decorative thin frame
    ov_draw.rectangle([16, 16, target_width - 16, target_height - 16], outline=(255, 182, 193, 200), width=2)
    ov_draw.rectangle([22, 22, target_width - 22, target_height - 22], outline=(255, 215, 0, 140), width=1)
    
    # Top Left: Japanese Seal / Stamp + Tgach Logo
    logo_size = 46
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (32, 28), logo_resized)
    
    # Red Stamp Badge with measured bounds (no text overflow!)
    badge_text = clean_text_for_font(slogan_dict.get("badge", "СЕКРЕТНО • /b/"))
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20)
    b_bbox = ov_draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = (b_bbox[2] - b_bbox[0]) + 20
    
    ov_draw.rounded_rectangle([88, 30, 88 + bw, 66], radius=4, fill=(190, 24, 38, 240), outline=(255, 215, 0, 220), width=1)
    ov_draw.text((98, 36), badge_text, font=badge_font, fill=(255, 255, 255, 255))
    
    ov_draw.text((88 + bw + 14, 36), f"ТГАЧ • {bot_username}", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24), fill=(255, 240, 245, 255))
    
    # Dark bottom card with soft pink/purple gradient
    for y in range(target_height - 320, target_height - 24):
        ratio = (y - (target_height - 320)) / 296
        alpha = int(246 * (ratio ** 1.1))
        ov_draw.line([(24, y), (target_width - 24, y)], fill=(18, 10, 26, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "АНОНИМНЫЙ ТГАЧ"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Уютные ночные треды и общение без правил."))
    
    max_text_w = target_width - 240
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, 21)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 45 - (len(hl_lines)*38) - (len(sub_lines)*26) - 20
    curr_y = start_y
    for line in hl_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            ov_draw.text((42 + ox, curr_y + oy), line, font=hl_font, fill=(0, 0, 0, 255))
        ov_draw.text((42, curr_y), line, font=hl_font, fill=(255, 140, 180, 255))
        curr_y += 38
        
    curr_y += 6
    for line in sub_lines:
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            ov_draw.text((42 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((42, curr_y), line, font=sub_font, fill=(255, 250, 252, 255))
        curr_y += 26
        
    ov_draw.text((42, target_height - 46), ">> СКАНИРУЙ QR ДЛЯ ВХОДА: " + bot_username, font=ImageFont.truetype(MAIN_FONT, 15), fill=(255, 215, 0, 255))
    
    # Sakura Pink QR Code
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#ff5599", back_color="#120818")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 38
    qr_box_y = target_height - qr_h - 48
    
    ov_draw.rounded_rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], radius=6, fill=(18, 8, 24, 255), outline=(255, 85, 153, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 14, qr_box_y + qr_h + 8), "|| SAKURA QR ||", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 11), fill=(255, 215, 0, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_terminal_matrix(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 6: Terminal / Matrix Hacker Aesthetic with Green Phosphor Glow & Monospace HUD."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # Top Green HUD Bar
    ov_draw.rectangle([0, 0, target_width, 64], fill=(6, 16, 8, 245))
    ov_draw.line([(0, 64), (target_width, 64)], fill=(0, 255, 102, 255), width=2)
    
    logo_size = 44
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (18, 10), logo_resized)
    
    ov_draw.text((74, 16), f"[SYS_ALERT: TGACH /{board_id}/ INFILTRATION]", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24), fill=(0, 255, 102, 255))
    
    # Bottom CRT Terminal Container
    for y in range(target_height - 310, target_height):
        ratio = (y - (target_height - 310)) / 310
        alpha = int(248 * (ratio ** 1.15))
        ov_draw.line([(0, y), (target_width, y)], fill=(4, 12, 6, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ПРОТОКОЛ АНОНИМНОСТИ"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Полный доступ к зашифрованным тредам борды."))
    
    max_text_w = target_width - 240
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font = ImageFont.truetype(MONO_FONT or MAIN_FONT, 20)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 40 - (len(hl_lines)*38) - (len(sub_lines)*26) - 25
    curr_y = start_y
    for line in hl_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=hl_font, fill=(0, 30, 10, 255))
        ov_draw.text((35, curr_y), line, font=hl_font, fill=(0, 255, 128, 255))
        curr_y += 38
        
    curr_y += 6
    for line in sub_lines:
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=sub_font, fill=(200, 255, 220, 255))
        curr_y += 26
        
    ov_draw.text((35, target_height - 35), "root@tgach:~# connect " + bot_username, font=ImageFont.truetype(MONO_FONT or MAIN_FONT, 15), fill=(0, 255, 102, 255))
    
    # Terminal Green Matrix QR Code
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#00ff66", back_color="#041006")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 30
    qr_box_y = target_height - qr_h - 45
    
    ov_draw.rounded_rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], radius=6, fill=(4, 14, 6, 255), outline=(0, 255, 102, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    ov_draw.text((qr_box_x + 8, qr_box_y + qr_h + 8), "[ACCESS_KEY]", font=ImageFont.truetype(MONO_FONT or MAIN_FONT, 11), fill=(0, 255, 102, 255))
    
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_soviet_propaganda(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 7: Constructivist Agitprop Poster with dynamic diagonals, red/cream/black palette, bold agit-typography."""
    canvas = Image.new("RGBA", (target_width, target_height), (244, 237, 224, 255))
    
    # High-contrast desaturated base image with red constructivist tint
    base_conv = base.convert("L").convert("RGBA")
    enhancer = ImageEnhance.Contrast(base_conv)
    base_conv = enhancer.enhance(1.30)
    
    red_tint = Image.new("RGBA", (target_width, target_height), (196, 24, 24, 80))
    base_conv = Image.alpha_composite(base_conv, red_tint)
    
    # Angled clipping wedge covering base area cleanly
    wedge_mask = Image.new("L", (target_width, target_height), 0)
    w_draw = ImageDraw.Draw(wedge_mask)
    w_draw.polygon([(0, 40), (target_width, 0), (target_width, target_height), (0, target_height)], fill=255)
    canvas.paste(base_conv, (0, 0), wedge_mask)
    
    draw = ImageDraw.Draw(canvas)
    
    # Top dynamic diagonal red wedge
    draw.polygon([(0, 0), (target_width, 0), (target_width, 70), (0, 110)], fill=(215, 25, 32, 255))
    draw.line([(0, 112), (target_width, 72)], fill=(245, 184, 0, 255), width=4)
    
    # Top agit banner
    top_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 28)
    draw.text((25, 20), "ТОВАРИЩ! ВСЯ ВЛАСТЬ АНОНАМ!", font=top_font, fill=(244, 237, 224, 255))
    
    b_label = f"/{board_id}/" if board_id else "/b/"
    board_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24)
    draw.text((target_width - 200, 22), f"ТГАЧ {b_label}", font=board_font, fill=(245, 184, 0, 255))
    
    # Red-gold constructivist logo
    sov_logo = draw_tgach_logo(52, bg_color=(215, 25, 32, 255))
    canvas.paste(sov_logo, (24, 126), sov_logo)
    
    # Agitprop Badge
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "АГИТПРОП /b/")).upper()
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20)
    badge_bbox = draw.textbbox((0, 0), badge_clean, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 24
    draw.rectangle([86, 132, 86 + badge_w, 170], fill=(22, 20, 20, 255))
    draw.text((98, 138), badge_clean, font=badge_font, fill=(245, 184, 0, 255))
    
    # Bottom Heavy Constructivist Card
    bottom_y = target_height - 280
    draw.polygon([
        (0, bottom_y),
        (target_width, bottom_y - 45),
        (target_width, target_height),
        (0, target_height)
    ], fill=(22, 20, 20, 252))
    
    draw.line([(0, bottom_y), (target_width, bottom_y - 45)], fill=(215, 25, 32, 255), width=6)
    draw.line([(0, bottom_y + 8), (target_width, bottom_y - 37)], fill=(245, 184, 0, 255), width=3)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ТЫ ЗАПИСАЛСЯ В ТГАЧ?!")).upper()
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Вступай в ряды анонимного сопротивления."))
    
    max_text_w = target_width - 240
    hl_font_size = 36
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, draw)
        
    sub_font_size = 20
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, draw)
    
    curr_y = bottom_y + 24
    for line in hl_lines:
        draw.text((34, curr_y), line, font=hl_font, fill=(245, 184, 0, 255))
        curr_y += hl_font_size + 6
        
    curr_y += 6
    for line in sub_lines:
        draw.text((34, curr_y), line, font=sub_font, fill=(244, 237, 224, 255))
        curr_y += sub_font_size + 5
        
    foot_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 16)
    draw.text((34, target_height - 36), f">> ПРИКАЗ №227: ВСТУПАЙ В {bot_username}", font=foot_font, fill=(215, 25, 32, 255))
    
    # Constructivist QR Code (Red on Cream)
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#c41818", back_color="#f4ede0")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 32
    qr_box_y = target_height - qr_h - 44
    
    draw.rectangle([qr_box_x - 8, qr_box_y - 8, qr_box_x + qr_w + 8, qr_box_y + qr_h + 8], fill=(244, 237, 224, 255), outline=(215, 25, 32, 255), width=3)
    canvas.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    
    tag_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12)
    tag_text = "|| СКАНИРУЙ ||"
    tw = draw.textlength(tag_text, font=tag_font)
    draw.text((qr_box_x + (qr_w - tw)//2, qr_box_y + qr_h + 10), tag_text, font=tag_font, fill=(245, 184, 0, 255))
    
    return canvas.convert("RGB")

def _render_layout_vhs_analog_horror(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 8: Analog Horror / VHS 1999 with interlaced scanlines, RGB chromatic split, OSD HUD and sinister tracking."""
    base_rgb = base.convert("RGB")
    r, g, b = base_rgb.split()
    
    # Chromatic shift (R shifted left 4px, B shifted right 4px)
    shift = 4
    r_shifted = Image.new("L", (target_width, target_height), 0)
    r_shifted.paste(r.crop((shift, 0, target_width, target_height)), (0, 0))
    
    b_shifted = Image.new("L", (target_width, target_height), 0)
    b_shifted.paste(b.crop((0, 0, target_width - shift, target_height)), (shift, 0))
    
    vhs_base = Image.merge("RGB", (r_shifted, g, b_shifted))
    vhs_base = ImageEnhance.Brightness(vhs_base).enhance(0.70)
    
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # CRT Interlaced Scanlines
    for y in range(0, target_height, 3):
        ov_draw.line([(0, y), (target_width, y)], fill=(0, 0, 0, 95), width=1)
        
    for y in range(110):
        a = int(220 * (1.0 - y / 110))
        ov_draw.line([(0, y), (target_width, y)], fill=(4, 6, 10, a))
        
    for y in range(target_height - 320, target_height):
        ratio = (y - (target_height - 320)) / 320
        a = int(250 * (ratio ** 1.2))
        ov_draw.line([(0, y), (target_width, y)], fill=(2, 4, 8, a))
        
    # Subtle VHS tracking glitch line
    glitch_y = target_height // 2 + 70
    ov_draw.rectangle([0, glitch_y, target_width, glitch_y + 8], fill=(20, 35, 50, 90))
    for gx in range(0, target_width, 8):
        if (gx // 8) % 2 == 0:
            ov_draw.line([(gx, glitch_y), (gx + 6, glitch_y)], fill=(180, 220, 255, 120), width=2)
            ov_draw.line([(gx, glitch_y + 4), (gx + 5, glitch_y + 4)], fill=(120, 180, 230, 80), width=1)
            
    # OSD Header: Vector triangle for play symbol
    osd_font = ImageFont.truetype(MONO_FONT or MAIN_FONT, 20)
    ov_draw.text((25, 20), "PLAY", font=osd_font, fill=(230, 245, 255, 240))
    ov_draw.polygon([(82, 23), (92, 29), (82, 35)], fill=(230, 245, 255, 240))
    ov_draw.text((100, 20), "02:44:19  SP", font=osd_font, fill=(230, 245, 255, 240))
    
    # Red blinking REC dot + text
    ov_draw.ellipse([target_width - 170, 24, target_width - 156, 38], fill=(240, 30, 30, 255))
    ov_draw.text((target_width - 148, 20), "REC  /b/", font=osd_font, fill=(240, 30, 30, 255))
    
    warn_font = ImageFont.truetype(MONO_FONT or MAIN_FONT, 15)
    ov_draw.text((25, 48), f"[ARCHIVE_FEED: TGACH_BOARD__{board_id.upper()}]", font=warn_font, fill=(0, 230, 255, 200))
    
    logo_size = 46
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (25, 78), logo_resized)
    
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "АНАЛОГОВЫЙ КОШМАР")).upper()
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18)
    badge_bbox = ov_draw.textbbox((0, 0), badge_clean, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 18
    ov_draw.rectangle([82, 85, 82 + badge_w, 117], fill=(180, 10, 20, 220), outline=(0, 230, 255, 220), width=1)
    ov_draw.text((91, 91), badge_clean, font=badge_font, fill=(255, 255, 255, 255))
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "СИГНАЛ НЕЛЬЗЯ ЗАГЛУШИТЬ"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Перехват анонимной трансляции. Заходи в тред."))
    
    max_text_w = target_width - 240
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font_size = 20
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 35 - (len(hl_lines)*(hl_font_size+6)) - (len(sub_lines)*(sub_font_size+6)) - 35
    curr_y = start_y
    for line in hl_lines:
        ov_draw.text((32, curr_y), line, font=hl_font, fill=(255, 20, 50, 200))
        ov_draw.text((38, curr_y), line, font=hl_font, fill=(0, 240, 255, 200))
        ov_draw.text((35, curr_y), line, font=hl_font, fill=(255, 255, 255, 255))
        curr_y += hl_font_size + 6
        
    curr_y += 8
    for line in sub_lines:
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            ov_draw.text((35 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((35, curr_y), line, font=sub_font, fill=(210, 240, 255, 255))
        curr_y += sub_font_size + 6
        
    ov_draw.text((35, target_height - 36), f">> BROADCAST KEY // TELEGRAM: {bot_username}", font=warn_font, fill=(0, 230, 255, 255))
    
    # Phosphor Cyan QR Code
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#00ffff", back_color="#040a12")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 30
    qr_box_y = target_height - qr_h - 45
    
    ov_draw.rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], fill=(4, 10, 18, 255), outline=(0, 230, 255, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    
    tag_font = ImageFont.truetype(MONO_FONT or MAIN_FONT, 11)
    ov_draw.text((qr_box_x + 6, qr_box_y + qr_h + 8), "[SIGNAL_DECODE]", font=tag_font, fill=(0, 230, 255, 255))
    
    return Image.alpha_composite(vhs_base.convert("RGBA"), overlay).convert("RGB")

def _render_layout_dark_gothic_scroll(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 9: Dark Gothic Inquisitorial Scroll with dark aged parchment, heraldic borders, wax seal, antique gold."""
    darkened = ImageEnhance.Brightness(base.convert("RGB")).enhance(0.58)
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    p1 = 20
    p2 = 28
    ov_draw.rectangle([p1, p1, target_width - p1, target_height - p1], outline=(180, 140, 60, 220), width=2)
    ov_draw.rectangle([p2, p2, target_width - p2, target_height - p2], outline=(120, 90, 40, 180), width=1)
    
    for cx, cy in [(p1, p1), (target_width - p1, p1), (p1, target_height - p1), (target_width - p1, target_height - p1)]:
        d = 7
        ov_draw.polygon([(cx - d, cy), (cx, cy - d), (cx + d, cy), (cx, cy + d)], fill=(225, 180, 70, 255))
        
    ov_draw.rectangle([p1 + 2, p1 + 2, target_width - p1 - 2, 74], fill=(18, 12, 14, 240))
    ov_draw.line([(p1 + 2, 74), (target_width - p1 - 2, 74)], fill=(180, 140, 60, 255), width=2)
    
    banner_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24)
    b_title = f"+ EDICTUM INQUISITIONIS + SACRA DVACHIA /{board_id}/ +"
    bw = ov_draw.textlength(b_title, font=banner_font)
    ov_draw.text(((target_width - bw)//2, 34), b_title, font=banner_font, fill=(225, 185, 75, 255))
    
    seal = draw_wax_seal(64)
    overlay.paste(seal, (36, 90), seal)
    
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "ЕРЕСЬ /b/")).upper()
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20)
    badge_bbox = ov_draw.textbbox((0, 0), badge_clean, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + 20
    ov_draw.rectangle([112, 102, 112 + badge_w, 140], fill=(130, 16, 24, 230), outline=(220, 175, 65, 230), width=1)
    ov_draw.text((122, 108), badge_clean, font=badge_font, fill=(245, 240, 230, 255))
    
    for y in range(target_height - 310, target_height - p1):
        ratio = (y - (target_height - 310)) / (310 - p1)
        a = int(250 * (ratio ** 1.1))
        ov_draw.line([(p1 + 2, y), (target_width - p1 - 2, y)], fill=(12, 8, 10, a))
        
    ov_draw.line([(p1 + 2, target_height - 310), (target_width - p1 - 2, target_height - 310)], fill=(180, 140, 60, 240), width=2)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ОСТАВЬ НАДЕЖДУ, ВСЯК СЮДА ВХОДЯЩИЙ"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Тайный орден анонимных еретиков ждет тебя."))
    
    max_text_w = target_width - 240
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font_size = 20
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    start_y = target_height - 40 - (len(hl_lines)*(hl_font_size+6)) - (len(sub_lines)*(sub_font_size+6)) - 30
    curr_y = start_y
    for line in hl_lines:
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)]:
            ov_draw.text((42 + ox, curr_y + oy), line, font=hl_font, fill=(100, 12, 18, 255))
        ov_draw.text((42, curr_y), line, font=hl_font, fill=(235, 195, 85, 255))
        curr_y += hl_font_size + 6
        
    curr_y += 6
    for line in sub_lines:
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            ov_draw.text((42 + ox, curr_y + oy), line, font=sub_font, fill=(0, 0, 0, 255))
        ov_draw.text((42, curr_y), line, font=sub_font, fill=(240, 235, 225, 255))
        curr_y += sub_font_size + 6
        
    ov_draw.text((42, target_height - 42), f"+ SIGILLUM HERETICUM: {bot_username} +", font=ImageFont.truetype(MAIN_FONT, 15), fill=(210, 165, 60, 255))
    
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#dfb74a", back_color="#140c0e")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - qr_w - 38
    qr_box_y = target_height - qr_h - 52
    
    ov_draw.rectangle([qr_box_x - 6, qr_box_y - 6, qr_box_x + qr_w + 6, qr_box_y + qr_h + 6], fill=(16, 10, 12, 255), outline=(190, 150, 60, 255), width=2)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    
    qtag_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 12)
    qtag = "+ SIGILLUM +"
    qtw = ov_draw.textlength(qtag, font=qtag_font)
    ov_draw.text((qr_box_x + (qr_w - qtw)//2, qr_box_y + qr_h + 8), qtag, font=qtag_font, fill=(225, 185, 75, 255))
    
    return Image.alpha_composite(darkened.convert("RGBA"), overlay).convert("RGB")

def _render_layout_brutalist_poster(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 10: Raw Swiss Brutalism with stark mono, acid yellow, hazard stripes and raw architectural grid."""
    canvas = Image.new("RGB", (target_width, target_height), (240, 240, 240))
    draw = ImageDraw.Draw(canvas)
    
    # Outer frame: 8px heavy black border
    draw.rectangle([0, 0, target_width - 1, target_height - 1], outline=(0, 0, 0), width=8)
    
    # Top header bar: Acid Yellow with Hazard Stripes
    top_h = 56
    draw.rectangle([8, 8, target_width - 8, top_h], fill=(255, 230, 0))
    draw.line([(8, top_h), (target_width - 8, top_h)], fill=(0, 0, 0), width=4)
    
    for sx in range(target_width - 160, target_width - 12, 14):
        draw.polygon([(sx, 8), (sx + 8, 8), (sx - 4, top_h), (sx - 12, top_h)], fill=(0, 0, 0))
        
    logo_size = 40
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    canvas.paste(logo_resized, (18, 12), logo_resized)
    
    head_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24)
    draw.text((68, 18), f"TGACH://BRUTAL_NET /{board_id}/", font=head_font, fill=(0, 0, 0))
    
    # Image frame in middle with aspect-ratio preserving crop
    pad = 20
    img_w = target_width - pad * 2
    img_h = int(target_height * 0.48)
    im_cropped = fit_and_crop(base.convert("RGB"), img_w, img_h)
    
    im_enh = ImageEnhance.Color(im_cropped).enhance(0.4)
    im_enh = ImageEnhance.Contrast(im_enh).enhance(1.2)
    canvas.paste(im_enh, (pad, top_h + 16))
    
    draw.rectangle([pad, top_h + 16, pad + img_w, top_h + 16 + img_h], outline=(0, 0, 0), width=4)
    
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "RAW INDUSTRIAL /b/")).upper()
    b_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18)
    b_bbox = draw.textbbox((0, 0), badge_clean, font=b_font)
    bw = (b_bbox[2] - b_bbox[0]) + 16
    draw.rectangle([pad + 8, top_h + 24, pad + 8 + bw, top_h + 52], fill=(0, 0, 0))
    draw.text((pad + 16, top_h + 28), badge_clean, font=b_font, fill=(255, 230, 0))
    
    # Bottom container: Stark Black
    bottom_y = top_h + 16 + img_h + 14
    draw.rectangle([pad, bottom_y, target_width - pad, target_height - pad], fill=(12, 12, 14))
    draw.rectangle([pad, bottom_y, target_width - pad, target_height - pad], outline=(0, 0, 0), width=4)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "НУЛЕВАЯ ТОЛЕРАНТНОСТЬ К СОЕ")).upper()
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Сырая правда без цензуры. Вступай."))
    
    max_text_w = target_width - 250
    hl_font_size = 32
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, draw)
        
    sub_font_size = 18
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, draw)
    
    curr_y = bottom_y + 18
    for line in hl_lines:
        draw.text((pad + 18, curr_y), line, font=hl_font, fill=(255, 230, 0))
        curr_y += hl_font_size + 4
        
    curr_y += 6
    for line in sub_lines:
        draw.text((pad + 18, curr_y), line, font=sub_font, fill=(240, 240, 240))
        curr_y += sub_font_size + 4
        
    draw.text((pad + 18, target_height - pad - 26), f"NODE://TG_{bot_username.upper()}", font=ImageFont.truetype(MONO_FONT or MAIN_FONT, 14), fill=(160, 160, 160))
    
    # Inverted High-Contrast QR Code (Acid Yellow on Black)
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#ffe600", back_color="#0c0c0e")
    qr_w, qr_h = qr_img.size
    qr_box_x = target_width - pad - qr_w - 16
    qr_box_y = bottom_y + 16
    
    draw.rectangle([qr_box_x - 4, qr_box_y - 4, qr_box_x + qr_w + 4, qr_box_y + qr_h + 4], fill=(12, 12, 14), outline=(255, 230, 0), width=2)
    canvas.paste(qr_img, (qr_box_x, qr_box_y))
    
    q_tag = "[ACCESS_NODE]"
    qw = draw.textlength(q_tag, font=ImageFont.truetype(MONO_FONT or MAIN_FONT, 11))
    draw.text((qr_box_x + (qr_w - qw)//2, qr_box_y + qr_h + 6), q_tag, font=ImageFont.truetype(MONO_FONT or MAIN_FONT, 11), fill=(255, 230, 0))
    
    return canvas

def _render_layout_comic_bubble(
    base: Image.Image,
    target_width: int,
    target_height: int,
    slogan_dict: Dict[str, str],
    board_id: str,
    bot_username: str,
    tgach_logo: Image.Image
) -> Image.Image:
    """Layout 11: Pop-Art Action Comic with speech bubble, action badges and vibrant high-energy layout."""
    canvas = Image.new("RGBA", (target_width, target_height), (20, 20, 30, 255))
    
    base_conv = ImageEnhance.Color(base.convert("RGB")).enhance(1.3)
    base_conv = ImageEnhance.Contrast(base_conv).enhance(1.15)
    
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # Top Comic Header
    ov_draw.rectangle([0, 0, target_width, 64], fill=(255, 215, 0, 255), outline=(0, 0, 0, 255), width=3)
    
    logo_size = 46
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (18, 9), logo_resized)
    
    ch_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 28)
    ov_draw.text((76, 16), f"TGACH COMICS: ISSUE #{board_id.upper()}", font=ch_font, fill=(0, 0, 0, 255))
    
    # Action Badge in corner
    badge_clean = clean_text_for_font(slogan_dict.get("badge", "ВБРОС ВЕКА!")).upper()
    badge_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20)
    badge_bbox = ov_draw.textbbox((0, 0), badge_clean, font=badge_font)
    bw = (badge_bbox[2] - badge_bbox[0]) + 20
    
    ov_draw.rectangle([target_width - bw - 28, 14, target_width - 16, 52], fill=(235, 30, 60, 255), outline=(0, 0, 0, 255), width=2)
    ov_draw.text((target_width - bw - 18, 18), badge_clean, font=badge_font, fill=(255, 255, 255, 255))
    
    # Bottom Speech Bubble Container
    bubble_y = target_height - 290
    bubble_x = 24
    bubble_w = target_width - 48
    bubble_h = 260
    
    tail_pts = [(120, bubble_y), (140, bubble_y - 28), (170, bubble_y)]
    ov_draw.polygon([(x + 5, y + 5) for x, y in tail_pts], fill=(0, 0, 0, 160))
    ov_draw.rounded_rectangle([bubble_x + 6, bubble_y + 6, bubble_x + bubble_w + 6, bubble_y + bubble_h + 6], radius=24, fill=(0, 0, 0, 160))
    
    ov_draw.polygon(tail_pts, fill=(255, 255, 255, 255))
    ov_draw.rounded_rectangle([bubble_x, bubble_y, bubble_x + bubble_w, bubble_y + bubble_h], radius=24, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)
    ov_draw.line([(120, bubble_y), (140, bubble_y - 28)], fill=(0, 0, 0, 255), width=4)
    ov_draw.line([(140, bubble_y - 28), (170, bubble_y)], fill=(0, 0, 0, 255), width=4)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "КТО ЗДЕСЬ СЫЧ? Я СЫЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Главный анонимный комикс рунета прямо в твоем телефоне."))
    
    max_text_w = bubble_w - 180
    hl_font_size = 34
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    while len(hl_lines) > 2 and hl_font_size > 22:
        hl_font_size -= 4
        hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
        hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
        
    sub_font_size = 20
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, sub_font_size)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    curr_y = bubble_y + 24
    for line in hl_lines:
        ov_draw.text((bubble_x + 24, curr_y), line, font=hl_font, fill=(225, 20, 45, 255))
        curr_y += hl_font_size + 4
        
    curr_y += 6
    for line in sub_lines:
        ov_draw.text((bubble_x + 24, curr_y), line, font=sub_font, fill=(30, 30, 35, 255))
        curr_y += sub_font_size + 4
        
    ov_draw.text((bubble_x + 24, bubble_y + bubble_h - 32), f">> JOIN: {bot_username}", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 16), fill=(0, 136, 204, 255))
    
    # Comic Barcode / QR Code
    qr_target = f"https://t.me/{bot_username.lstrip('@')}"
    qr_img = generate_qr(qr_target, box_size=4, border=1, fill_color="#000000", back_color="#ffffff")
    qr_w, qr_h = qr_img.size
    qr_box_x = bubble_x + bubble_w - qr_w - 22
    qr_box_y = bubble_y + 22
    
    ov_draw.rectangle([qr_box_x - 4, qr_box_y - 4, qr_box_x + qr_w + 4, qr_box_y + qr_h + 4], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
    overlay.paste(qr_img, (qr_box_x, qr_box_y), qr_img)
    
    lbl = "|| SCAN NOW ||"
    lw = ov_draw.textlength(lbl, font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 11))
    ov_draw.text((qr_box_x + (qr_w - lw)//2, qr_box_y + qr_h + 8), lbl, font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 11), fill=(0, 0, 0, 255))
    
    return Image.alpha_composite(base_conv.convert("RGBA"), overlay).convert("RGB")


# ==========================================
# STYLE REGISTRY & ALIAS RESOLUTION
# ==========================================

INVITE_LAYOUT_STYLES = list(range(12))

STYLE_NAMES: Dict[int, str] = {
    0: "CYBER_BOARD",
    1: "DEMOTIVATOR_2CH",
    2: "CYBER_PLAQUE",
    3: "VAPOR_NEON",
    4: "BREAKING_NEWS",
    5: "ANIME_JAPAN_CARD",
    6: "TERMINAL_MATRIX",
    7: "SOVIET_PROPAGANDA",
    8: "VHS_ANALOG_HORROR",
    9: "DARK_GOTHIC_SCROLL",
    10: "BRUTALIST_POSTER",
    11: "COMIC_BUBBLE",
}

STYLE_ALIASES: Dict[str, int] = {
    "cyber_board": 0,
    "cyber": 0,
    "default": 0,
    "demotivator": 1,
    "demotivator_2ch": 1,
    "dem": 1,
    "cyber_plaque": 2,
    "plaque": 2,
    "glass": 2,
    "vapor_neon": 3,
    "retro_vaporwave": 3,
    "vaporwave": 3,
    "neon": 3,
    "breaking_news": 4,
    "newspaper_frontpage": 4,
    "news": 4,
    "anime_japan": 5,
    "anime_japan_card": 5,
    "anime": 5,
    "sakura": 5,
    "terminal_matrix": 6,
    "neon_terminal": 6,
    "terminal": 6,
    "matrix": 6,
    "hacker": 6,
    "soviet_propaganda": 7,
    "soviet": 7,
    "constructivism": 7,
    "agitprop": 7,
    "vhs_analog_horror": 8,
    "analog_horror": 8,
    "vhs": 8,
    "glitch": 8,
    "dark_gothic_scroll": 9,
    "gothic_scroll": 9,
    "gothic": 9,
    "inquisition": 9,
    "brutalist_poster": 10,
    "brutalist": 10,
    "swiss": 10,
    "comic_bubble": 11,
    "comic": 11,
    "popart": 11,
}

def resolve_layout_style(layout: Optional[Union[int, str]]) -> int:
    """Normalizes numeric or string layout identifier to a valid integer style ID."""
    if layout is None:
        return random.choice(INVITE_LAYOUT_STYLES)
    if isinstance(layout, int):
        return layout if layout in STYLE_NAMES else 0
    clean_str = str(layout).strip().lower().replace("-", "_")
    return STYLE_ALIASES.get(clean_str, 0)

# ==========================================
# PUBLIC API
# ==========================================

def build_invite_image_card(
    base_image: Optional[Image.Image] = None,
    slogan_dict: Optional[Union[Dict[str, str], str]] = None,
    board_id: str = "b",
    bot_username: str = "@dvach_chatbot",
    site_url: Optional[str] = None,
    custom_text: Optional[str] = None,
    text: Optional[str] = None,
    layout_style: Optional[Union[int, str]] = None
) -> io.BytesIO:
    """
    Renders a complete, high-quality graphic invite card using one of 12 distinct layouts.
    """
    target_width, target_height = 800, 800
    
    if base_image is None:
        base = create_procedural_background(target_width, target_height, style=random.randint(0, 1))
    else:
        base = fit_and_crop(base_image.convert("RGB"), target_width, target_height)
        enhancer = ImageEnhance.Brightness(base)
        base = enhancer.enhance(0.72)
    
    tgach_logo = draw_tgach_logo(64)
    
    raw_input_text = custom_text or text
    if isinstance(slogan_dict, str):
        raw_input_text = slogan_dict
        slogan_dict = None
        
    if not slogan_dict:
        if raw_input_text:
            slogan_dict = {
                "badge": "ДВАЧ • ТГАЧ /b/",
                "headline": raw_input_text,
                "subline": f"Анонимный чат в телеге: {bot_username}"
            }
        else:
            slogan_dict = random.choice(IMAGE_SLOGANS)
            
    resolved_style = resolve_layout_style(layout_style)
        
    if resolved_style == 1:
        final_img = _render_layout_demotivator(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 2:
        final_img = _render_layout_cyber_plaque(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 3:
        final_img = _render_layout_vapor_neon(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 4:
        final_img = _render_layout_breaking_news(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 5:
        final_img = _render_layout_anime_japan(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 6:
        final_img = _render_layout_terminal_matrix(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 7:
        final_img = _render_layout_soviet_propaganda(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 8:
        final_img = _render_layout_vhs_analog_horror(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 9:
        final_img = _render_layout_dark_gothic_scroll(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 10:
        final_img = _render_layout_brutalist_poster(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif resolved_style == 11:
        final_img = _render_layout_comic_bubble(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    else:
        final_img = _render_layout_cyber_board(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
        
    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    return buf

async def generate_invite_image_async(
    board_id: str = "b",
    bot_username: str = "@dvach_chatbot",
    slogan_dict: Optional[Union[Dict[str, str], str]] = None,
    custom_text: Optional[str] = None,
    layout_style: Optional[Union[int, str]] = None,
    bot: Optional[Any] = None
) -> io.BytesIO:
    """High-level async helper to generate a complete invite image card."""
    base_img = await fetch_random_post_image(board_id=board_id, bot=bot)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: build_invite_image_card(
            base_image=base_img,
            slogan_dict=slogan_dict,
            custom_text=custom_text,
            board_id=board_id,
            bot_username=bot_username,
            layout_style=layout_style
        )
    )

def get_random_auto_invite_content(board_id: str = "b", bot_username: str = "@dvach_chatbot") -> Tuple[Dict[str, str], str]:
    """
    Returns a pair of (image_slogan_dict, companion_caption_text)
    guaranteeing that on-image text and message caption are distinct and unique.
    """
    slogan = random.choice(IMAGE_SLOGANS)
    caption = random.choice(AUTO_POST_COMPANION_TEXTS)
    caption = caption.replace("@dvach_chatbot", bot_username).replace("@tgchan_chatbot", bot_username)
    return slogan, caption

def render_custom_demotivator(
    base_image: Optional[Image.Image] = None,
    title: str = "ШИЗОФРЕНИЯ",
    subtitle: Optional[str] = None,
    bot_username: str = "@dvach_chatbot"
) -> io.BytesIO:
    """
    Renders a classic high-impact 2ch Demotivator with dual frame, centered Impact title,
    subline, and crisp Tgach vector badge.
    """
    target_width, target_height = 800, 850
    canvas = Image.new("RGB", (target_width, target_height), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    img_box_w = 680
    img_box_h = 520
    img_box_x = (target_width - img_box_w) // 2
    img_box_y = 50
    
    if base_image is None:
        img_content = create_procedural_background(img_box_w, img_box_h, style=1)
    else:
        img_content = fit_and_crop(base_image.convert("RGB"), img_box_w, img_box_h)
        
    canvas.paste(img_content, (img_box_x, img_box_y))
    
    border_pad = 6
    draw.rectangle(
        [
            img_box_x - border_pad,
            img_box_y - border_pad,
            img_box_x + img_box_w + border_pad,
            img_box_y + img_box_h + border_pad
        ],
        outline=(255, 255, 255),
        width=3
    )
    
    title_clean = clean_text_for_font(title.strip().upper())
    subtitle_clean = clean_text_for_font(subtitle.strip()) if subtitle else ""
    
    title_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 38)
    sub_font = ImageFont.truetype(MAIN_FONT, 20)
    
    title_lines = wrap_text(title_clean, title_font, target_width - 80, draw)
    sub_lines = wrap_text(subtitle_clean, sub_font, target_width - 100, draw) if subtitle_clean else []
    
    curr_y = img_box_y + img_box_h + 35
    for line in title_lines:
        w = draw.textlength(line, font=title_font)
        x = (target_width - w) // 2
        draw.text((x, curr_y), line, font=title_font, fill=(255, 255, 255))
        curr_y += 44
        
    curr_y += 6
    for line in sub_lines:
        w = draw.textlength(line, font=sub_font)
        x = (target_width - w) // 2
        draw.text((x, curr_y), line, font=sub_font, fill=(220, 220, 220))
        curr_y += 26
        
    logo = draw_tgach_logo(36)
    logo_w, logo_h = logo.size
    canvas.paste(logo, (target_width - logo_w - 20, target_height - logo_h - 15), logo)
    draw.text((target_width - logo_w - 180, target_height - 28), f"ТГАЧ /b/ • {bot_username}", font=ImageFont.truetype(MAIN_FONT, 13), fill=(120, 120, 120))
    
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=93, optimize=True)
    buf.seek(0)
    return buf

async def generate_custom_demotivator_async(
    base_image: Optional[Image.Image] = None,
    title: str = "ШИЗОФРЕНИЯ",
    subtitle: Optional[str] = None,
    bot_username: str = "@dvach_chatbot"
) -> io.BytesIO:
    """Non-blocking async runner for custom demotivators."""
    if base_image is None:
        base_image = await fetch_random_post_image()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: render_custom_demotivator(
            base_image=base_image,
            title=title,
            subtitle=subtitle,
            bot_username=bot_username
        )
    )
