# invite_image_generator.py
"""
Graphic Invite Card Generator for Dvachbot (Тгач)
Generates stylized, high-impact invitation cards with random media, vector Tgach logo, QR codes,
7 distinct visual layout styles, and a massive collection of authentic Dvachean slogans.
"""

import os
import io
import sys
import random
import re
import asyncio
import sqlite3
import aiohttp
from typing import Optional, Tuple, Dict, List, Union
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
try:
    import qrcode
except ImportError:
    qrcode = None



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

def clean_text_for_font(text: str) -> str:
    """Removes unsupported emoji glyphs from text for clean TTF rendering."""
    if not text:
        return ""
    cleaned = EMOJI_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

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
    
    draw.polygon(shadow_poly, fill=(0, 65, 110, 170))
    draw.polygon(poly, fill=(255, 255, 255, 255))
    
    return img.resize((size, size), Image.Resampling.LANCZOS)

def create_procedural_background(width: int = 800, height: int = 800, style: int = 0) -> Image.Image:
    """Generates an atmospheric procedural Dvach image with noise, grid and watermark."""
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
        
    watermark_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(watermark_overlay)
    wm_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 190)
    wm_draw.text((width // 2 - 210, height // 2 - 130), "2ch", font=wm_font, fill=(255, 140, 0, 38))
    
    glow_color = (255, 130, 0, 35) if style == 0 else (160, 40, 240, 35)
    wm_draw.ellipse([width//4, height//4, 3*width//4, 3*height//4], fill=glow_color)
    watermark_overlay = watermark_overlay.filter(ImageFilter.GaussianBlur(radius=30))
    
    img = Image.alpha_composite(img.convert("RGBA"), watermark_overlay).convert("RGB")
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

async def fetch_random_post_image(db_path: Optional[str] = None, bot: Optional[Any] = None) -> Optional[Image.Image]:
    """
    Selects a random authentic background image strictly from user posts (111,000+ photos) and Booru URLs in DB.
    """
    if not db_path:
        db_path = os.path.join(_BASE_DIR, "dvach_bot.db")
        
    candidates = []
    file_id_candidates = []
    if os.path.exists(db_path):
        try:
            from common.db_pool import get_pool, db_lock
            async with db_lock:
                db = await get_pool()
                # 1. Sample from 111,594+ real user photos
                async with db.execute("""
                    SELECT original_file_id, original_url FROM PostFiles 
                    WHERE file_type = 'photo' AND original_file_id IS NOT NULL
                    ORDER BY RANDOM() LIMIT 40
                """) as cursor:
                    rows = await cursor.fetchall()
                for fid, url in rows:
                    if url and url.startswith("http"):
                        candidates.append(url)
                    elif fid and fid.startswith("http"):
                        candidates.append(fid)
                    elif fid:
                        file_id_candidates.append(fid)
                
                # 2. Check Posts content JSON for image_url
                if len(candidates) < 10:
                    async with db.execute("""
                        SELECT content FROM Posts 
                        WHERE content LIKE '%http%' AND (content LIKE '%.jpg%' OR content LIKE '%.png%' OR content LIKE '%.jpeg%')
                        ORDER BY RANDOM() LIMIT 40
                    """) as cursor:
                        p_rows = await cursor.fetchall()
                    for (cnt_str,) in p_rows:
                        try:
                            cnt = json.loads(cnt_str)
                            u = cnt.get('image_url') or cnt.get('url')
                            if not u and cnt.get('type') == 'media_group' and 'media' in cnt:
                                for m in cnt['media']:
                                    if m.get('type') == 'photo':
                                        u = m.get('media') or m.get('file_id')
                                        break
                            if u and str(u).startswith('http'):
                                candidates.append(str(u))
                        except Exception:
                            pass
        except Exception:
            def _get_sync():
                res_urls = []
                res_fids = []
                try:
                    conn = sqlite3.connect(db_path, timeout=5.0)
                    c = conn.cursor()
                    c.execute("""
                        SELECT original_file_id, original_url FROM PostFiles 
                        WHERE file_type = 'photo' AND original_file_id IS NOT NULL
                        ORDER BY RANDOM() LIMIT 40
                    """)
                    for fid, url in c.fetchall():
                        if url and url.startswith("http"):
                            res_urls.append(url)
                        elif fid and fid.startswith("http"):
                            res_urls.append(fid)
                        elif fid:
                            res_fids.append(fid)
                    conn.close()
                except Exception:
                    pass
                return res_urls, res_fids
            candidates, file_id_candidates = await asyncio.to_thread(_get_sync)

    # 1. Try downloading real user photo via Bot API if bot instance is available
    if bot and file_id_candidates:
        random.shuffle(file_id_candidates)
        for fid in file_id_candidates[:3]:
            try:
                buf = io.BytesIO()
                await bot.download(fid, destination=buf)
                buf.seek(0)
                if buf.getbuffer().nbytes > 4000:
                    img = Image.open(buf)
                    img.verify()
                    buf.seek(0)
                    return Image.open(buf).convert("RGB")
            except Exception:
                continue

    # 2. Try HTTP URLs from DB
    if candidates:
        random.shuffle(candidates)
        timeout = aiohttp.ClientTimeout(total=3.0)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for url in candidates[:8]:
                    try:
                        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                if len(data) > 4000:
                                    img = Image.open(io.BytesIO(data))
                                    img.verify()
                                    return Image.open(io.BytesIO(data)).convert("RGB")
                    except Exception:
                        continue
        except Exception:
            pass

    return None

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
    """Layout 1: Classic 2ch Demotivator Poster Style with solid black border & centered headline."""
    frame_img = Image.new("RGB", (target_width, target_height), (8, 8, 12))
    pad_x, pad_top = 40, 36
    inner_w = target_width - (pad_x * 2)
    inner_h = int(target_height * 0.62)
    
    cropped_base = base.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
    frame_img.paste(cropped_base, (pad_x, pad_top))
    
    draw = ImageDraw.Draw(frame_img)
    draw.rectangle([pad_x - 4, pad_top - 4, pad_x + inner_w + 4, pad_top + inner_h + 4], outline=(255, 255, 255, 220), width=2)
    
    logo_size = 42
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    frame_img.paste(logo_resized, (pad_x + 12, pad_top + 12), logo_resized)
    
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "ЗАХОДИ В ТГАЧ!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Анонимный чат прямо в телеграме."))
    
    hl_font_size = 38
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, hl_font_size)
    max_w = target_width - 240
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
    
    ov_draw.rounded_rectangle([40, card_y + 18, 40 + len(badge_clean)*11 + 16, card_y + 46], radius=4, fill=(0, 136, 204, 240))
    ov_draw.text((48, card_y + 22), badge_clean, font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18), fill=(255, 255, 255, 255))
    
    max_text_w = target_width - 240
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 32)
    hl_lines = wrap_text(headline_clean, hl_font, max_text_w, ov_draw)
    
    sub_font = ImageFont.truetype(MAIN_FONT or IMPACT_FONT, 20)
    sub_lines = wrap_text(subline_clean, sub_font, max_text_w, ov_draw)
    
    curr_y = card_y + 56
    for line in hl_lines:
        ov_draw.text((40, curr_y), line, font=hl_font, fill=(255, 185, 45, 255))
        curr_y += 36
        
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
        
    ov_draw.text((35, target_height - 35), "★ СКАНИРУЙ QR-КОД ★ " + bot_username, font=ImageFont.truetype(MAIN_FONT, 15), fill=(255, 0, 128, 255))
    
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
    """Layout 4: Breaking News Alert Style with Red/Blue Ticker Banner & Radar Frame."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    ov_draw.rectangle([0, 0, target_width, 60], fill=(204, 0, 0, 245))
    logo_size = 44
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (16, 8), logo_resized)
    
    ov_draw.text((70, 14), "⚡ ЭКСТРЕННЫЙ ВЫПУСК /B/ • ТГАЧ NEWS", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 26), fill=(255, 255, 255, 255))
    
    ov_draw.rectangle([0, 60, target_width, 90], fill=(255, 204, 0, 245))
    ov_draw.text((20, 66), f"МАССОВЫЙ ВБРОС НА ДОСКЕ /{board_id}/ >> {bot_username} >> АНОНЫ В АХУЕ >>", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 18), fill=(0, 0, 0, 255))
    
    for y in range(target_height - 300, target_height):
        ratio = (y - (target_height - 300)) / 300
        alpha = int(250 * (ratio ** 1.15))
        ov_draw.line([(0, y), (target_width, y)], fill=(8, 8, 12, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "СРОЧНО В НОМЕР!"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Главные события анонимного рунета."))
    
    max_text_w = target_width - 240
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 34)
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
    """Layout 5: Japanese Anime Aesthetic with Kanji accents, cherry gold frame, red seal & neon pink QR."""
    overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    
    # Outer gold/sakura decorative thin frame
    ov_draw.rectangle([16, 16, target_width - 16, target_height - 16], outline=(255, 182, 193, 200), width=2)
    ov_draw.rectangle([22, 22, target_width - 22, target_height - 22], outline=(255, 215, 0, 140), width=1)
    
    # Top Left: Japanese Seal / Stamp + Tgach Logo
    logo_size = 46
    logo_resized = tgach_logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
    overlay.paste(logo_resized, (32, 28), logo_resized)
    
    # Red Stamp Badge
    ov_draw.rounded_rectangle([88, 30, 210, 66], radius=4, fill=(190, 24, 38, 240), outline=(255, 215, 0, 220), width=1)
    ov_draw.text((96, 36), "СЕКРЕТНО • /b/", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 20), fill=(255, 255, 255, 255))
    
    ov_draw.text((220, 36), f"ТГАЧ • {bot_username}", font=ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 24), fill=(255, 240, 245, 255))
    
    # Dark bottom card with soft pink/purple gradient
    for y in range(target_height - 320, target_height - 24):
        ratio = (y - (target_height - 320)) / 296
        alpha = int(246 * (ratio ** 1.1))
        ov_draw.line([(24, y), (target_width - 24, y)], fill=(18, 10, 26, alpha))
        
    headline_clean = clean_text_for_font(slogan_dict.get("headline", "АНОНИМНЫЙ ТГАЧ"))
    subline_clean = clean_text_for_font(slogan_dict.get("subline", "Уютные ночные треды и общение без правил."))
    
    max_text_w = target_width - 240
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 34)
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
    hl_font = ImageFont.truetype(IMPACT_FONT or MAIN_FONT, 34)
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

def build_invite_image_card(
    base_image: Optional[Image.Image] = None,
    slogan_dict: Optional[Union[Dict[str, str], str]] = None,
    board_id: str = "b",
    bot_username: str = "@dvach_chatbot",
    site_url: Optional[str] = None,
    custom_text: Optional[str] = None,
    text: Optional[str] = None,
    layout_style: Optional[int] = None
) -> io.BytesIO:
    """
    Renders a complete, high-quality graphic invite card using one of 7 distinct layouts.
    """
    target_width, target_height = 800, 800
    
    if base_image is None:
        base = create_procedural_background(target_width, target_height, style=random.randint(0, 1))
    else:
        img = base_image.convert("RGB")
        w, h = img.size
        scale = max(target_width / w, target_height / h)
        nw, nh = int(w * scale), int(h * scale)
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        
        left = (nw - target_width) // 2
        top = (nh - target_height) // 2
        base = img.crop((left, top, left + target_width, top + target_height))
        
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
            
    if layout_style is None:
        layout_style = random.choice([0, 1, 2, 3, 4, 5, 6])
        
    if layout_style == 1:
        final_img = _render_layout_demotivator(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif layout_style == 2:
        final_img = _render_layout_cyber_plaque(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif layout_style == 3:
        final_img = _render_layout_vapor_neon(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif layout_style == 4:
        final_img = _render_layout_breaking_news(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif layout_style == 5:
        final_img = _render_layout_anime_japan(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    elif layout_style == 6:
        final_img = _render_layout_terminal_matrix(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
    else:
        final_img = _render_layout_cyber_board(base, target_width, target_height, slogan_dict, board_id, bot_username, tgach_logo)
        
    buf = io.BytesIO()
    final_img.save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    return buf

INVITE_LAYOUT_STYLES = [0, 1, 2, 3, 4, 5, 6]
STYLE_NAMES = {
    0: "CYBER_BOARD",
    1: "DEMOTIVATOR_2CH",
    2: "CYBER_PLAQUE",
    3: "VAPOR_NEON",
    4: "BREAKING_NEWS",
    5: "ANIME_JAPAN_CARD",
    6: "TERMINAL_MATRIX"
}

async def generate_invite_image_async(
    board_id: str = "b",
    bot_username: str = "@dvach_chatbot",
    slogan_dict: Optional[Union[Dict[str, str], str]] = None,
    custom_text: Optional[str] = None,
    layout_style: Optional[int] = None,
    bot: Optional[Any] = None
) -> io.BytesIO:
    """High-level async helper to generate a complete invite image card."""
    base_img = await fetch_random_post_image(bot=bot)
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
        im = base_image.convert("RGB")
        w, h = im.size
        scale = max(img_box_w / w, img_box_h / h)
        nw, nh = int(w * scale), int(h * scale)
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - img_box_w) // 2
        top = (nh - img_box_h) // 2
        img_content = im.crop((left, top, left + img_box_w, top + img_box_h))
        
    canvas.paste(img_content, (img_box_x, img_box_y))
    
    # Classic Demotivator white border frame around image
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
    
    # Typography
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
        
    # Tgach watermark in bottom-right corner
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

