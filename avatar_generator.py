# -*- coding: utf-8 -*-
"""
avatar_generator.py — High-Definition Dvachean RPG Character & Avatar Card Generator
Renders a complete RPG character sheet with visual paperdoll layering for:
- Headwear: Foil Hat, VIP Crown, Neko Ears, Bag, Helmet, Tophat
- Face / Glasses: Thug Life Glasses, Wasserman Glasses, Anonymous Mask, Clown Nose
- Torso: Wasserman Vest, Tracksuit, Asuka Hoodie, Neo Cloak, Straitjacket
- Feet / Shoes: Slippers with socks, Riot Boots, Velvet Sneakers (Podkraduli)
- Hands: Knife, Pepper Spray, Shit, Mute-Gun, Partyvan, Shield
- Aura: Custom badge color radiance (Red, Green, Blue, Purple, Gold, Orange, White, Black, Rainbow)
- Set Bonuses: Dynamic detection of matching sets
- Stats: Toxicity, Defense, Sanity, Net Worth, Debuffs
"""

import os
import io
import time
import json
import random
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(_BASE_DIR, "fonts")
IMPACT_FONT = os.path.join(FONTS_DIR, "Impact.ttf") if os.path.exists(os.path.join(FONTS_DIR, "Impact.ttf")) else None
MAIN_FONT = os.path.join(_BASE_DIR, "font1.ttf") if os.path.exists(os.path.join(_BASE_DIR, "font1.ttf")) else None

COLOR_PALETTE = {
    "red": {"hex": "#FF3344", "emoji": "🔴", "name": "Кроваво-красный", "aura": (255, 50, 70, 80)},
    "green": {"hex": "#00FF66", "emoji": "🟢", "name": "Кислотно-зеленый", "aura": (0, 255, 100, 80)},
    "blue": {"hex": "#00CCFF", "emoji": "🔵", "name": "Неоново-синий", "aura": (0, 200, 255, 80)},
    "purple": {"hex": "#CC33FF", "emoji": "🟣", "name": "Аметистовый", "aura": (200, 50, 255, 80)},
    "gold": {"hex": "#FFD700", "emoji": "🟡", "name": "Имперское золото", "aura": (255, 215, 0, 80)},
    "orange": {"hex": "#FF8800", "emoji": "🟠", "name": "Радиоактивный оранж", "aura": (255, 136, 0, 80)},
    "white": {"hex": "#F0F0FF", "emoji": "⚪", "name": "Платиновый", "aura": (240, 240, 255, 80)},
    "black": {"hex": "#33333D", "emoji": "🏴", "name": "Теневой", "aura": (50, 50, 60, 100)},
    "rainbow": {"hex": "#FF007F", "emoji": "🌈", "name": "Голографический", "aura": (255, 0, 128, 90)},
}

def get_font(size: int, font_path: Optional[str] = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = font_path or MAIN_FONT or IMPACT_FONT
    if path and os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def build_character_card(
    user_id: int,
    anon_id: str,
    balance: float,
    posts_count: int,
    active_items: Dict[str, Any],
    custom_prefix: Optional[str] = None,
    badge_color: Optional[str] = None,
    cursed_until: int = 0
) -> io.BytesIO:
    """
    Generates an 800x1050px RPG Character Sheet for Telegram imageboards.
    """
    from wardrobe_engine import CLOTHING_CATALOG, get_active_set_bonuses
    W, H = 800, 1050
    img = Image.new("RGBA", (W, H), (14, 14, 18, 255))
    draw = ImageDraw.Draw(img)

    now_ts = int(time.time())

    # 1. Background Grid & Synthwave Glow
    for y in range(0, H, 20):
        alpha = int(18 + (y / H) * 22)
        draw.line([(0, y), (W, y)], fill=(32, 34, 46, alpha), width=1)
    for x in range(0, W, 20):
        draw.line([(x, 0), (x, H)], fill=(32, 34, 46, 18), width=1)

    # Accent color & border
    color_info = COLOR_PALETTE.get(badge_color or "gold", COLOR_PALETTE["gold"])
    accent_hex = color_info["hex"]
    accent_rgb = tuple(int(accent_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    # Outer border glow
    draw.rectangle([10, 10, W-10, H-10], outline=accent_rgb, width=3)
    draw.rectangle([14, 14, W-14, H-14], outline=(38, 40, 52, 255), width=1)

    # 2. Header Banner
    draw.rectangle([15, 15, W-15, 88], fill=(22, 24, 32, 255))
    font_title = get_font(30, IMPACT_FONT)
    draw.text((35, 28), "ТГАЧ RPG // КАРТОЧКА ПЕРСОНАЖА", fill=(255, 255, 255), font=font_title)

    badge_tag = f"{color_info['emoji']} {color_info['name'].upper()}" if badge_color else "⚪ ОБЫЧНЫЙ АНОН"
    font_sub = get_font(16)
    draw.text((W - 270, 36), badge_tag, fill=accent_rgb, font=font_sub)

    # 3. Paperdoll Avatar Frame (Left: 35..315, Top: 105..465)
    avatar_box = [35, 105, 315, 465]
    draw.rectangle(avatar_box, fill=(18, 20, 26, 255), outline=accent_rgb, width=2)

    center_x = (avatar_box[0] + avatar_box[2]) // 2
    center_y = (avatar_box[1] + avatar_box[3]) // 2

    # Aura glow behind avatar
    draw.ellipse([center_x - 70, center_y - 80, center_x + 70, center_y + 80], fill=color_info["aura"])

    # Base Anonymous Silhouette
    # Torso Base
    torso_color = (48, 52, 64)
    eq_torso = active_items.get("equipped_torso")
    if eq_torso == "body_wasserman": torso_color = (160, 130, 80)
    elif eq_torso == "body_tracksuit": torso_color = (30, 70, 150)
    elif eq_torso == "body_hoodie": torso_color = (200, 40, 50)
    elif eq_torso == "body_cloak": torso_color = (25, 25, 30)
    elif eq_torso == "body_straitjacket": torso_color = (220, 220, 220)

    draw.polygon([
        (center_x - 55, center_y + 115),
        (center_x + 55, center_y + 115),
        (center_x + 35, center_y + 20),
        (center_x - 35, center_y + 20)
    ], fill=torso_color, outline=(80, 85, 100), width=1)

    # Head Circle Base
    head_color = (68, 74, 90)
    draw.ellipse([center_x - 38, center_y - 60, center_x + 38, center_y + 16], fill=head_color, outline=(90, 95, 110), width=2)

    # Face Gear (Glasses / Mask / Nose)
    eq_face = active_items.get("equipped_face")
    if eq_face == "face_thug_glasses":
        draw.rectangle([center_x - 32, center_y - 32, center_x + 32, center_y - 18], fill=(10, 10, 10), outline=(255, 255, 255), width=1)
        draw.text((center_x - 22, center_y - 32), "⌐■-■", fill=(255, 255, 255), font=get_font(15))
    elif eq_face == "face_wasserman_glasses":
        draw.ellipse([center_x - 30, center_y - 32, center_x - 6, center_y - 14], outline=(255, 215, 0), width=2)
        draw.ellipse([center_x + 6, center_y - 32, center_x + 30, center_y - 14], outline=(255, 215, 0), width=2)
        draw.line([(center_x - 6, center_y - 23), (center_x + 6, center_y - 23)], fill=(255, 215, 0), width=2)
    elif eq_face == "face_anon_mask":
        draw.text((center_x - 14, center_y - 36), "🎭", font=get_font(24))
    elif eq_face == "face_clown_nose":
        draw.ellipse([center_x - 8, center_y - 24, center_x + 8, center_y - 8], fill=(255, 20, 40), outline=(200, 0, 0), width=1)
    else:
        # Default eyes
        draw.ellipse([center_x - 20, center_y - 28, center_x - 10, center_y - 18], fill=(255, 255, 255))
        draw.ellipse([center_x + 10, center_y - 28, center_x + 20, center_y - 18], fill=(255, 255, 255))
        draw.ellipse([center_x - 16, center_y - 25, center_x - 12, center_y - 21], fill=(0, 0, 0))
        draw.ellipse([center_x + 12, center_y - 25, center_x + 16, center_y - 21], fill=(0, 0, 0))

    # Headwear Gear Layer
    eq_head = active_items.get("equipped_head")
    has_tinfoil = (active_items.get("tinfoil_hat", 0) > now_ts or active_items.get("tinfoil_until", 0) > now_ts or eq_head == "hat_tinfoil")
    if has_tinfoil:
        draw.polygon([
            (center_x - 42, center_y - 48),
            (center_x, center_y - 110),
            (center_x + 42, center_y - 48)
        ], fill=(200, 210, 225), outline=(255, 255, 255), width=2)
    elif eq_head == "hat_crown" or custom_prefix:
        draw.polygon([
            (center_x - 38, center_y - 48),
            (center_x - 30, center_y - 85),
            (center_x - 10, center_y - 65),
            (center_x, center_y - 95),
            (center_x + 10, center_y - 65),
            (center_x + 30, center_y - 85),
            (center_x + 38, center_y - 48)
        ], fill=(255, 215, 0), outline=(255, 240, 150), width=1)
    elif eq_head == "hat_cat_ears":
        draw.polygon([(center_x - 36, center_y - 45), (center_x - 48, center_y - 85), (center_x - 16, center_y - 58)], fill=(255, 120, 180), outline=(255, 255, 255), width=1)
        draw.polygon([(center_x + 36, center_y - 45), (center_x + 48, center_y - 85), (center_x + 16, center_y - 58)], fill=(255, 120, 180), outline=(255, 255, 255), width=1)
    elif eq_head == "hat_bag":
        draw.rectangle([center_x - 46, center_y - 72, center_x + 46, center_y + 12], fill=(210, 180, 130), outline=(140, 100, 50), width=2)
        draw.text((center_x - 18, center_y - 45), "👀", font=get_font(20))
    elif eq_head == "hat_helmet":
        draw.ellipse([center_x - 48, center_y - 78, center_x + 48, center_y - 25], fill=(40, 45, 55), outline=(0, 200, 255), width=2)
        draw.rectangle([center_x - 38, center_y - 45, center_x + 38, center_y - 28], fill=(0, 200, 255, 180))
    elif eq_head == "hat_tophat":
        draw.rectangle([center_x - 30, center_y - 115, center_x + 30, center_y - 66], fill=(20, 20, 25), outline=(255, 215, 0), width=1)
        draw.ellipse([center_x - 48, center_y - 72, center_x + 48, center_y - 62], fill=(20, 20, 25), outline=(255, 215, 0), width=1)

    # --- Shield & Weapons Hand Layers ---
    has_shield = active_items.get("shield_until", 0) > now_ts or active_items.get("reflect_shield_until", 0) > now_ts
    if has_shield:
        draw.ellipse([center_x - 92, center_y + 15, center_x - 44, center_y + 90], fill=(0, 180, 255, 170), outline=(255, 255, 255), width=2)
        draw.text((center_x - 76, center_y + 38), "🛡️", font=get_font(22))

    # Weapon Icon
    weapon_icon = "👊"
    if active_items.get("partyvan_gun"): weapon_icon = "🚔"
    elif active_items.get("knife_gun"): weapon_icon = "🔪"
    elif active_items.get("pepperspray_gun"): weapon_icon = "🧯"
    elif active_items.get("mute_gun"): weapon_icon = "🔇"
    elif active_items.get("shit_gun"): weapon_icon = "💩"
    elif active_items.get("laxative_gun"): weapon_icon = "🚽"
    elif active_items.get("schizopill_gun"): weapon_icon = "💊"

    draw.ellipse([center_x + 44, center_y + 30, center_x + 92, center_y + 80], fill=(45, 48, 58), outline=accent_rgb, width=1)
    draw.text((center_x + 56, center_y + 42), weapon_icon, font=get_font(22))

    # 4. Identity & Stats Box (Right: 335..765, Top: 105..465)
    stats_box = [335, 105, 765, 465]
    draw.rectangle(stats_box, fill=(20, 22, 28, 255), outline=(40, 44, 56), width=1)

    font_hdr = get_font(23, IMPACT_FONT)
    draw.text((355, 118), f"АНОНИМ: #{anon_id}", fill=(255, 255, 255), font=font_hdr)

    if custom_prefix:
        draw.text((355, 148), f"👑 {custom_prefix}", fill=(255, 215, 0), font=get_font(17))
    else:
        draw.text((355, 148), f"Ранг: Постоянный Анон (Постов: {posts_count})", fill=(170, 175, 185), font=get_font(16))

    # Balance Plate (Hidden if Anonymous Mask is equipped!)
    draw.rectangle([355, 178, 745, 238], fill=(28, 30, 38, 255), outline=accent_rgb, width=1)
    draw.text((370, 188), "💳 ГЛОБАЛЬНЫЙ БАЛАНС:", fill=(160, 165, 175), font=get_font(14))
    if eq_face == "face_anon_mask":
        draw.text((370, 206), "🎭 [СКРЫТО МАСКОЙ АНОНИМУСА]", fill=(200, 200, 220), font=get_font(18, IMPACT_FONT))
    else:
        draw.text((370, 206), f"{int(balance):,} ₪ (Шекелей)".replace(',', ' '), fill=(0, 255, 150), font=get_font(22, IMPACT_FONT))

    # Dynamic RPG Attributes
    has_curse = cursed_until > now_ts or active_items.get("cursed_until", 0) > now_ts
    has_shit = active_items.get("shit_until", 0) > now_ts

    tox_val = min(100, int(15 + posts_count * 0.04 + (30 if active_items.get("knife_gun") else 0) + (40 if active_items.get("partyvan_gun") else 0)))
    def_val = min(100, (45 if has_tinfoil else 5) + (35 if has_shield else 0) + (25 if active_items.get("pepperspray_gun") else 0))
    san_val = max(0, 100 - (50 if has_curse else 0) - (30 if has_shit else 0) - min(40, posts_count // 120))
    wealth_val = min(100, int((balance / 1500) * 100))

    # Apply Set Bonus stats if present
    active_sets = get_active_set_bonuses(active_items)
    for s in active_sets:
        tox_val = max(0, min(100, tox_val + s.get("bonus_toxicity", 0)))
        def_val = max(0, min(100, def_val + s.get("bonus_defense", 0)))
        san_val = max(0, min(100, san_val + s.get("bonus_sanity", 0)))

    unl_ach = active_items.get("unlocked_achievements", [])
    ach_txt = f"🏆 Трофеи: {len(unl_ach)}/12"
    draw.text((355, 250), "📊 RPG ХАРАКТЕРИСТИКИ:", fill=(255, 255, 255), font=get_font(16, IMPACT_FONT))
    draw.text((630, 252), ach_txt, fill=(255, 215, 0), font=get_font(13))

    def draw_attribute(y: int, label: str, val: int, color: Tuple[int, int, int]):
        draw.text((355, y), f"{label}: {val}%", fill=(200, 205, 215), font=get_font(13))
        draw.rectangle([510, y + 2, 745, y + 15], fill=(36, 38, 48), outline=(55, 58, 70), width=1)
        w = int((val / 100) * (745 - 512))
        if w > 0:
            draw.rectangle([512, y + 4, 512 + w, y + 13], fill=color)

    draw_attribute(278, "⚔️ Токсичность", tox_val, (255, 55, 65))
    draw_attribute(308, "🛡️ Защита", def_val, (0, 200, 255))
    draw_attribute(338, "🧠 Рассудок", san_val, (190, 70, 255))
    draw_attribute(368, "💰 Богатство", wealth_val, (255, 215, 0))

    # Set Bonus Ribbon if active
    if active_sets:
        set_text = f"✨ СЕТ: {active_sets[0]['name']}"
        draw.rectangle([355, 405, 745, 455], fill=(45, 30, 65), outline=(255, 215, 0), width=1)
        draw.text((365, 412), set_text, fill=(255, 235, 120), font=get_font(13))
        draw.text((365, 432), active_sets[0]['bonus_desc'][:46] + "...", fill=(200, 190, 220), font=get_font(11))

    # 5. Wardrobe & Equipment Slots (35..765, Top: 485..1030)
    wardrobe_box = [35, 480, 765, 1025]
    draw.rectangle(wardrobe_box, fill=(18, 20, 26, 255), outline=(40, 44, 56), width=1)
    draw.text((55, 492), "🎒 АКТИВНАЯ ЭКИПИРОВКА И СЛОТЫ:", fill=(255, 255, 255), font=font_hdr)

    # Build Slot Descriptions
    eq_feet = active_items.get("equipped_feet")
    head_name = CLOTHING_CATALOG.get(eq_head, {}).get("name") if eq_head in CLOTHING_CATALOG else ("👽 Шапочка из фольги" if has_tinfoil else ("👑 VIP Корона" if custom_prefix else "Голова без убора"))
    torso_name = CLOTHING_CATALOG.get(eq_torso, {}).get("name") if eq_torso in CLOTHING_CATALOG else "Обычная футболка анона"
    face_name = CLOTHING_CATALOG.get(eq_face, {}).get("name") if eq_face in CLOTHING_CATALOG else "Чистое лицо (Без очков/маски)"
    feet_name = CLOTHING_CATALOG.get(eq_feet, {}).get("name") if eq_feet in CLOTHING_CATALOG else "Босиком (Без обуви)"

    weapon_name = "Кулак (Без оружия)"
    if active_items.get("partyvan_gun"): weapon_name = "🚔 Пативэн-Ган"
    elif active_items.get("knife_gun"): weapon_name = "🔪 Заточка"
    elif active_items.get("pepperspray_gun"): weapon_name = "🧯 Перцовый баллончик"
    elif active_items.get("mute_gun"): weapon_name = "🔇 Мут-Ган"
    elif active_items.get("shit_gun"): weapon_name = "💩 Кусок говна"

    slots = [
        ("СЛОТ: ГОЛОВНОЙ УБОР", head_name, bool(eq_head or has_tinfoil or custom_prefix)),
        ("СЛОТ: ОДЕЖДА / ТОРС", torso_name, bool(eq_torso)),
        ("СЛОТ: ЛИЦО / ОЧКИ", face_name, bool(eq_face)),
        ("СЛОТ: ОБУВЬ / ПЕДАЛИ", feet_name, bool(eq_feet)),
        ("СЛОТ: ПРАВАЯ РУКА (ОРУЖИЕ)", weapon_name, bool(weapon_icon != "👊")),
        ("СЛОТ: ЛЕВАЯ РУКА (ЩИТ)", "🛡️ Зеркальный Щит (Активен)" if has_shield else "Пусто", has_shield),
        ("СЛОТ: АВТО-ЗАЩИТА", "🧯 Перцовка (Готова к защите)" if active_items.get("pepperspray_gun") else "Пусто (Беззащитен)", bool(active_items.get("pepperspray_gun"))),
        ("СЛОТ: АУРА И ЦВЕТ НИКА", f"{color_info['emoji']} {color_info['name']}" if badge_color else "Стандартный серый", bool(badge_color)),
        ("ДЕБАФФЫ И СТАТУС", "🚽 ПРОКЛЯТИЕ ПОНОСА (/curse)" if has_curse else ("💩 ОБМАЗАН ГОВНОМ (/shit)" if has_shit else "✅ Здоров (Чист)"), bool(has_curse or has_shit)),
    ]

    slot_y = 530
    for slot_title, slot_content, is_act in slots:
        draw.rectangle([55, slot_y, 745, slot_y + 44], fill=(26, 28, 36, 255) if is_act else (20, 22, 28, 255), outline=accent_rgb if is_act else (38, 40, 50), width=1)
        draw.text((70, slot_y + 6), slot_title, fill=(135, 140, 155), font=get_font(11))
        txt_col = (255, 255, 255) if is_act else (100, 105, 115)
        draw.text((70, slot_y + 20), slot_content, fill=txt_col, font=get_font(15))
        slot_y += 50

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def build_character_html_card(
    user_id: int,
    anon_id: str,
    balance: float,
    posts_count: int,
    active_items: dict,
    custom_prefix: Optional[str] = None,
    badge_color: Optional[str] = None,
    cursed_until: int = 0
) -> str:
    """
    Generates a lightning-fast formatted HTML text character sheet with zero PIL image rendering overhead.
    """
    from wardrobe_engine import get_active_set_bonuses, CLOTHING_CATALOG
    active_sets = get_active_set_bonuses(active_items)

    equipped_head = active_items.get("equipped_head")
    equipped_torso = active_items.get("equipped_torso")
    equipped_face = active_items.get("equipped_face")
    equipped_feet = active_items.get("equipped_feet")

    has_tinfoil = active_items.get("tinfoil_hat", 0) > time.time()
    has_shield = active_items.get("shield_active", 0) > time.time()
    has_curse = cursed_until > time.time()
    has_shit = active_items.get("shit_covered_until", 0) > time.time()

    head_name = CLOTHING_CATALOG.get(equipped_head, {}).get("name") if equipped_head in CLOTHING_CATALOG else ("👽 Шапочка из фольги" if has_tinfoil else ("👑 VIP Корона" if custom_prefix else "<i>(Пусто)</i>"))
    torso_name = CLOTHING_CATALOG.get(equipped_torso, {}).get("name", "<i>(Пусто)</i>")
    face_name = CLOTHING_CATALOG.get(equipped_face, {}).get("name", "<i>(Пусто)</i>")
    feet_name = CLOTHING_CATALOG.get(equipped_feet, {}).get("name", "<i>(Пусто)</i>")

    weapon_name = "👊 Кулак (Без оружия)"
    if active_items.get("partyvan_gun"): weapon_name = "🚔 Пативэн-Ган"
    elif active_items.get("knife_gun"): weapon_name = "🔪 Заточка"
    elif active_items.get("pepperspray_gun"): weapon_name = "🧯 Перцовый баллончик"
    elif active_items.get("mute_gun"): weapon_name = "🔇 Мут-Ган"
    elif active_items.get("shit_gun"): weapon_name = "💩 Кусок говна"

    # RPG Stats calculation
    toxicity = min(100, max(5, int(posts_count * 1.5) % 100))
    defense = 10
    if has_shield: defense += 40
    if equipped_head == "hat_helmet": defense += 30
    for s in active_sets:
        if s.get("id") == "set_riot_police": defense += 20
    defense = min(100, defense)

    sanity = 100
    if has_curse: sanity = 15
    elif active_items.get("schizopill_active", 0) > time.time(): sanity = 40
    elif equipped_torso == "body_straitjacket": sanity = 25

    wealth = min(100, int(balance / 50))

    def make_bar(val: int) -> str:
        filled = int(val / 10)
        return "█" * filled + "░" * (10 - filled)

    # Trophies
    from achievements_engine import ACHIEVEMENTS_CATALOG
    unlocked = active_items.get("unlocked_achievements", [])
    ach_cnt = len(unlocked)
    total_ach = len(ACHIEVEMENTS_CATALOG)

    is_masked = (equipped_face == "face_anon_mask")
    bal_str = "🎭 [ЗАСЕКРЕЧЕНО]" if is_masked else f"{int(balance):,} ₪"

    color_info = COLOR_PALETTE.get(badge_color, {"name": "Стандартный", "emoji": "⚪️"})

    lines = [
        f"🎭 <b>ДОСЬЕ И КАРТОЧКА ПЕРСОНАЖА [#{anon_id}]</b>",
        f"<code>{'—'*28}</code>",
        f"👤 <b>Статус:</b> {custom_prefix if custom_prefix else 'Битард'} | <b>Аура:</b> {color_info['emoji']} {color_info['name']}",
        f"💰 <b>Капитал:</b> <code>{bal_str}</code> | <b>Постов:</b> <code>{posts_count}</code>",
        f"🏆 <b>Трофеи:</b> <code>{ach_cnt}/{total_ach}</code> ({int(ach_cnt/total_ach*100)}%)",
        "",
        "📊 <b>RPG ХАРАКТЕРИСТИКИ:</b>",
        f"⚔️ Токсичность: <code>[{make_bar(toxicity)}]</code> {toxicity}%",
        f"🛡️ Защита:      <code>[{make_bar(defense)}]</code> {defense}%",
        f"🧠 Рассудок:    <code>[{make_bar(sanity)}]</code> {sanity}%",
        f"💎 Богатство:   <code>[{make_bar(wealth)}]</code> {wealth}%",
        "",
        "🥋 <b>ЭКИПИРОВКА И СЛОТЫ:</b>",
        f"🎩 <b>Голова:</b>  {head_name}",
        f"🧥 <b>Торс:</b>    {torso_name}",
        f"👓 <b>Лицо:</b>    {face_name}",
        f"👟 <b>Обувь:</b>   {feet_name}",
        f"⚔️ <b>Оружие:</b>  {weapon_name}",
        f"🛡️ <b>Щит:</b>     {'🛡️ Зеркальный Щит' if has_shield else '<i>(Пусто)</i>'}",
    ]

    if has_curse or has_shit:
        debuff = "🚽 Проклятие поноса" if has_curse else "💩 Обмазан говном"
        lines.append(f"⚠️ <b>Дебафф:</b> {debuff}")

    if active_sets:
        lines.append("")
        for s in active_sets:
            lines.append(f"✨ <b>СЕТ-БОНУС:</b> {s['name']}\n<i>{s['bonus_desc']}</i>")

    lines.append(f"<code>{'—'*28}</code>")
    lines.append("💡 <i>Одевайся в /wardrobe, вооружайся в /shop и выполняй /ach!</i>")

    return "\n".join(lines)
