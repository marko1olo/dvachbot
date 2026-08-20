# -*- coding: utf-8 -*-
"""
combat_visuals.py — Visual HD Posters for Dvach Duels, Robberies, Pepper Spray, and Combat.
"""

import os
import io
import random
from PIL import Image, ImageDraw, ImageFont
from common.anon_identity import get_anon_id, generate_anon_name


def _get_combat_font(size: int, bold: bool = True):
    paths = [
        "fonts/Impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "fonts/ocra.ttf",
        "font1.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_duel_poster(winner_id: int, loser_id: int, amount: int, board_id: str = "b", winner_prefix: str = None, loser_prefix: str = None) -> io.BytesIO:
    """
    Генерирует HD 960x540 плакат результатов дуэли между двумя анонами.
    """
    W, H = 960, 540
    img = Image.new("RGBA", (W, H), (14, 17, 24, 255))
    draw = ImageDraw.Draw(img)

    f_head = _get_combat_font(22, bold=True)
    f_badge = _get_combat_font(13, bold=True)
    f_title = _get_combat_font(23, bold=True)
    f_huge = _get_combat_font(34, bold=True)
    f_label = _get_combat_font(13, bold=False)
    f_vs = _get_combat_font(28, bold=True)

    # 1. Grid background dots
    for x in range(25, W - 25, 28):
        for y in range(25, H - 25, 28):
            draw.point((x, y), fill=(28, 36, 50, 255))

    # Outer border
    draw.rounded_rectangle([14, 14, W - 14, H - 14], radius=16, outline=(42, 54, 78, 255), width=2)

    # 2. Header
    draw.rounded_rectangle([36, 26, W - 36, 76], radius=10, fill=(20, 26, 38, 255), outline=(48, 62, 88, 255), width=1)
    draw.text((54, 38), "РЕЗУЛЬТАТ СМЕРТЕЛЬНОЙ ДУЭЛИ", font=f_head, fill=(255, 215, 0, 255))
    draw.text((W - 170, 42), f"ДОСКА /{board_id}/", font=f_badge, fill=(140, 160, 190, 255))

    # 3. Left Fighter Card (WINNER)
    card_w, card_h = 360, 310
    lx, ly = 48, 96
    draw.rounded_rectangle([lx, ly, lx + card_w, ly + card_h], radius=14, fill=(16, 28, 22, 255), outline=(0, 230, 140, 200), width=2)

    # Winner Pill
    draw.rounded_rectangle([lx + 20, ly + 18, lx + 140, ly + 48], radius=6, fill=(0, 200, 120, 255))
    draw.text((lx + 30, ly + 24), "ПОБЕДИТЕЛЬ", font=f_badge, fill=(10, 25, 18, 255))

    # Winner Avatar
    av_s = 64
    draw.rounded_rectangle([lx + 20, ly + 64, lx + 20 + av_s, ly + 64 + av_s], radius=10, fill=(22, 40, 30, 255), outline=(0, 230, 140, 255), width=2)
    rng_w = random.Random(winner_id)
    grid_w = [[rng_w.random() > 0.45 for _ in range(3)] for _ in range(5)]
    pw = 8
    for r in range(5):
        for c in range(3):
            if grid_w[r][c]:
                draw.rectangle([lx + 32 + c * pw, ly + 76 + r * pw, lx + 32 + (c + 1) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(0, 230, 140, 255))
                if c < 2:
                    draw.rectangle([lx + 32 + (4 - c) * pw, ly + 76 + r * pw, lx + 32 + (5 - c) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(0, 230, 140, 255))

    w_tag = f"Анон [{get_anon_id(winner_id)}]"
    draw.text((lx + 98, ly + 72), w_tag, font=f_title, fill=(240, 255, 245, 255))
    pfx_w = f"Титул: [{winner_prefix}]" if winner_prefix else "Мастер клинка борды"
    draw.text((lx + 98, ly + 102), pfx_w, font=f_label, fill=(120, 175, 145, 255))

    # Win Loot Box
    draw.rounded_rectangle([lx + 20, ly + 150, lx + card_w - 20, ly + 280], radius=10, fill=(12, 20, 16, 255), outline=(0, 200, 120, 70), width=1)
    draw.text((lx + 36, ly + 168), "ВЫИГРЫШ В ДУЭЛИ:", font=f_label, fill=(120, 175, 145, 255))
    draw.text((lx + 36, ly + 196), f"+{amount:,} ₪", font=f_huge, fill=(0, 240, 150, 255))
    draw.text((lx + 36, ly + 248), "Шекели зачислены на баланс", font=f_label, fill=(90, 140, 115, 255))

    # 4. Center Clash VS Area
    cx = W // 2
    draw.ellipse([cx - 44, 205, cx + 44, 293], fill=(22, 28, 40, 255), outline=(255, 200, 50, 255), width=2)
    draw.text((cx - 18, 232), "VS", font=f_vs, fill=(255, 215, 0, 255))

    draw.text((cx - 30, 318), "СТАВКА", font=f_badge, fill=(120, 140, 170, 255))
    st_txt = f"{amount:,} ₪"
    st_w = draw.textlength(st_txt, font=f_head)
    draw.text((cx - st_w / 2, 338), st_txt, font=f_head, fill=(255, 230, 50, 255))

    # 5. Right Fighter Card (LOSER)
    rx = W - card_w - 48
    draw.rounded_rectangle([rx, ly, rx + card_w, ly + card_h], radius=14, fill=(28, 16, 18, 255), outline=(255, 70, 75, 180), width=2)

    # Loser Pill
    draw.rounded_rectangle([rx + 20, ly + 18, rx + 140, ly + 48], radius=6, fill=(220, 45, 55, 255))
    draw.text((rx + 30, ly + 24), "ПОВЕРЖЕН", font=f_badge, fill=(255, 240, 240, 255))

    # Loser Avatar
    draw.rounded_rectangle([rx + 20, ly + 64, rx + 20 + av_s, ly + 64 + av_s], radius=10, fill=(38, 22, 25, 255), outline=(255, 70, 75, 255), width=2)
    rng_l = random.Random(loser_id)
    grid_l = [[rng_l.random() > 0.45 for _ in range(3)] for _ in range(5)]
    for r in range(5):
        for c in range(3):
            if grid_l[r][c]:
                draw.rectangle([rx + 32 + c * pw, ly + 76 + r * pw, rx + 32 + (c + 1) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(255, 75, 85, 255))
                if c < 2:
                    draw.rectangle([rx + 32 + (4 - c) * pw, ly + 76 + r * pw, rx + 32 + (5 - c) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(255, 75, 85, 255))

    l_tag = f"Анон [{get_anon_id(loser_id)}]"
    draw.text((rx + 98, ly + 72), l_tag, font=f_title, fill=(255, 235, 235, 255))
    pfx_l = f"Титул: [{loser_prefix}]" if loser_prefix else "Повержен в честном бою"
    draw.text((rx + 98, ly + 102), pfx_l, font=f_label, fill=(180, 125, 130, 255))

    # Loss Box
    draw.rounded_rectangle([rx + 20, ly + 150, rx + card_w - 20, ly + 280], radius=10, fill=(20, 12, 14, 255), outline=(220, 45, 55, 70), width=1)
    draw.text((rx + 36, ly + 168), "ПОТЕРЯНО В ДУЭЛИ:", font=f_label, fill=(180, 125, 130, 255))
    draw.text((rx + 36, ly + 196), f"-{amount:,} ₪", font=f_huge, fill=(255, 75, 85, 255))
    draw.text((rx + 36, ly + 248), "Списано с баланса", font=f_label, fill=(150, 95, 100, 255))

    # 6. Bottom Banner
    draw.rounded_rectangle([48, 430, W - 48, 495], radius=10, fill=(20, 25, 36, 255), outline=(38, 48, 68, 255), width=1)
    draw.text((70, 452), "Судьба борды беспощадна: монета решила исход битвы.", font=f_label, fill=(210, 225, 245, 255))
    draw.text((W - 220, 452), "/duel — бросить вызов", font=f_badge, fill=(255, 215, 40, 255))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


def draw_rob_poster(robber_id: int, victim_id: int, amount: int, outcome: str = "success", board_id: str = "b") -> io.BytesIO:
    """
    Генерирует HD 960x540 плакат результатов ограбления (гоп-стоп, фольга, перцовка).
    """
    W, H = 960, 540
    img = Image.new("RGBA", (W, H), (14, 16, 22, 255))
    draw = ImageDraw.Draw(img)

    f_head = _get_combat_font(22, bold=True)
    f_badge = _get_combat_font(13, bold=True)
    f_title = _get_combat_font(23, bold=True)
    f_huge = _get_combat_font(34, bold=True)
    f_label = _get_combat_font(13, bold=False)

    # 1. Grid dots
    for x in range(25, W - 25, 28):
        for y in range(25, H - 25, 28):
            draw.point((x, y), fill=(28, 34, 46, 255))

    # Theme colors
    if outcome == "success":
        border_color = (255, 60, 80, 255)
        header_title = "🔪 ТЕНЕВОЙ ГОП-СТОП (ЗАТОЧКА)"
        header_color = (255, 80, 80, 255)
    elif outcome == "pepperspray":
        border_color = (255, 140, 30, 255)
        header_title = "🧯 КОНТР-АТАКА: ПЕРЦОВЫЙ БАЛЛОНЧИК!"
        header_color = (255, 150, 40, 255)
    else:  # tinfoil
        border_color = (0, 200, 255, 255)
        header_title = "👽 ОТРАЖЕНИЕ ШАПОЧКОЙ ИЗ ФОЛЬГИ"
        header_color = (0, 220, 255, 255)

    draw.rounded_rectangle([14, 14, W - 14, H - 14], radius=16, outline=border_color, width=2)

    # 2. Header
    draw.rounded_rectangle([36, 26, W - 36, 76], radius=10, fill=(20, 24, 34, 255), outline=(42, 52, 70, 255), width=1)
    draw.text((54, 38), header_title, font=f_head, fill=header_color)
    draw.text((W - 170, 42), f"РАЗДЕЛ /{board_id}/", font=f_badge, fill=(130, 150, 180, 255))

    # 3. Left Card (ROBBER / ATTACKER)
    card_w, card_h = 360, 310
    lx, ly = 48, 96

    robber_bg = (26, 16, 20, 255) if outcome == "success" else (24, 18, 16, 255)
    robber_border = (255, 75, 85, 200) if outcome == "success" else (255, 120, 50, 180)
    draw.rounded_rectangle([lx, ly, lx + card_w, ly + card_h], radius=14, fill=robber_bg, outline=robber_border, width=2)

    # Robber Pill
    rob_pill_color = (220, 50, 60, 255) if outcome == "success" else (220, 100, 40, 255)
    rob_pill_text = "ГРАБИТЕЛЬ" if outcome == "success" else ("ОСЛЕПЛЕН" if outcome == "pepperspray" else "САМОПОРЕЗ")
    draw.rounded_rectangle([lx + 20, ly + 18, lx + 140, ly + 48], radius=6, fill=rob_pill_color)
    draw.text((lx + 30, ly + 24), rob_pill_text, font=f_badge, fill=(255, 240, 240, 255))

    # Avatar Robber
    av_s = 64
    draw.rounded_rectangle([lx + 20, ly + 64, lx + 20 + av_s, ly + 64 + av_s], radius=10, fill=(36, 22, 26, 255), outline=robber_border, width=2)
    rng_r = random.Random(robber_id)
    grid_r = [[rng_r.random() > 0.45 for _ in range(3)] for _ in range(5)]
    pw = 8
    for r in range(5):
        for c in range(3):
            if grid_r[r][c]:
                draw.rectangle([lx + 32 + c * pw, ly + 76 + r * pw, lx + 32 + (c + 1) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(255, 75, 85, 255))
                if c < 2:
                    draw.rectangle([lx + 32 + (4 - c) * pw, ly + 76 + r * pw, lx + 32 + (5 - c) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=(255, 75, 85, 255))

    draw.text((lx + 98, ly + 72), f"Анон [{get_anon_id(robber_id)}]", font=f_title, fill=(255, 235, 235, 255))
    if outcome == "success":
        r_sub = "Орудует заточкой из /shop"
    elif outcome == "pepperspray":
        r_sub = "Залит перцем и потерял деньги"
    else:
        r_sub = "В панике порезался сам"
    draw.text((lx + 98, ly + 102), r_sub, font=f_label, fill=(180, 125, 130, 255))

    # Robber Amount Box
    draw.rounded_rectangle([lx + 20, ly + 150, lx + card_w - 20, ly + 280], radius=10, fill=(18, 12, 14, 255), outline=(220, 50, 60, 70), width=1)
    if outcome == "success":
        draw.text((lx + 36, ly + 168), "УКРАДЕНО ШЕКЕЛЕЙ:", font=f_label, fill=(180, 125, 130, 255))
        draw.text((lx + 36, ly + 196), f"+{amount:,} ₪", font=f_huge, fill=(0, 240, 140, 255))
        draw.text((lx + 36, ly + 248), "Сумма украдена из карманов жертвы", font=f_label, fill=(150, 100, 105, 255))
    else:
        draw.text((lx + 36, ly + 168), "ПОТЕРЯНО НА ПАНИКЕ:", font=f_label, fill=(180, 125, 130, 255))
        draw.text((lx + 36, ly + 196), f"-{amount:,} ₪", font=f_huge, fill=(255, 75, 85, 255))
        draw.text((lx + 36, ly + 248), "Шекели высыпались из штанов грабителя", font=f_label, fill=(150, 100, 105, 255))

    # 4. Center Icon
    cx = W // 2
    draw.ellipse([cx - 44, 205, cx + 44, 293], fill=(22, 28, 38, 255), outline=header_color, width=2)
    badge_label = "ROB" if outcome == "success" else ("SPRAY" if outcome == "pepperspray" else "SHIELD")
    draw.text((cx - 18, 234), badge_label, font=f_badge, fill=header_color)

    draw.text((cx - 26, 318), "КУШ", font=f_badge, fill=(120, 140, 170, 255))
    st_txt = f"{amount:,} ₪"
    st_w = draw.textlength(st_txt, font=f_head)
    draw.text((cx - st_w / 2, 338), st_txt, font=f_head, fill=(255, 220, 50, 255))

    # 5. Right Card (VICTIM)
    rx = W - card_w - 48
    if outcome == "success":
        victim_bg = (18, 14, 16, 255)
        victim_border = (200, 80, 80, 120)
        vic_pill_color = (160, 60, 70, 255)
        vic_pill_text = "ЖЕРТВА"
        av_col = (180, 100, 100, 255)
    elif outcome == "pepperspray":
        victim_bg = (16, 26, 18, 255)
        victim_border = (0, 230, 140, 200)
        vic_pill_color = (0, 200, 120, 255)
        vic_pill_text = "🧯 ПЕРЦОВКА СРАБОТАЛА"
        av_col = (0, 230, 140, 255)
    else:
        victim_bg = (14, 26, 30, 255)
        victim_border = (0, 220, 255, 200)
        vic_pill_color = (0, 180, 240, 255)
        vic_pill_text = "👽 ФОЛЬГА"
        av_col = (0, 220, 255, 255)

    draw.rounded_rectangle([rx, ly, rx + card_w, ly + card_h], radius=14, fill=victim_bg, outline=victim_border, width=2)
    draw.rounded_rectangle([rx + 20, ly + 18, rx + 190, ly + 48], radius=6, fill=vic_pill_color)
    draw.text((rx + 26, ly + 24), vic_pill_text, font=f_badge, fill=(10, 20, 30, 255) if outcome != "success" else (255, 240, 240, 255))

    # Victim Avatar
    draw.rounded_rectangle([rx + 20, ly + 64, rx + 20 + av_s, ly + 64 + av_s], radius=10, fill=(24, 28, 38, 255), outline=victim_border, width=2)
    rng_v = random.Random(victim_id)
    grid_v = [[rng_v.random() > 0.45 for _ in range(3)] for _ in range(5)]
    for r in range(5):
        for c in range(3):
            if grid_v[r][c]:
                draw.rectangle([rx + 32 + c * pw, ly + 76 + r * pw, rx + 32 + (c + 1) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=av_col)
                if c < 2:
                    draw.rectangle([rx + 32 + (4 - c) * pw, ly + 76 + r * pw, rx + 32 + (5 - c) * pw - 1, ly + 76 + (r + 1) * pw - 1], fill=av_col)

    draw.text((rx + 98, ly + 72), f"Анон [{get_anon_id(victim_id)}]", font=f_title, fill=(245, 245, 250, 255))
    if outcome == "success":
        v_sub = "Ограблен в темном переулке"
    elif outcome == "pepperspray":
        v_sub = "Обезвредил нападающего струей перца"
    else:
        v_sub = "Защищен Шапочкой из фольги"
    draw.text((rx + 98, ly + 102), v_sub, font=f_label, fill=(140, 160, 180, 255))

    # Victim Box
    draw.rounded_rectangle([rx + 20, ly + 150, rx + card_w - 20, ly + 280], radius=10, fill=(14, 18, 24, 255), outline=victim_border, width=1)
    if outcome == "success":
        draw.text((rx + 36, ly + 168), "УБЫТОК ПРИ ГОП-СТОПЕ:", font=f_label, fill=(180, 130, 135, 255))
        draw.text((rx + 36, ly + 196), f"-{amount:,} ₪", font=f_huge, fill=(255, 75, 85, 255))
        draw.text((rx + 36, ly + 248), "Купи Перцовку или Фольгу в /shop", font=f_label, fill=(140, 100, 105, 255))
    elif outcome == "pepperspray":
        draw.text((rx + 36, ly + 168), "КОМПЕНСАЦИЯ ЗА НАПАДЕНИЕ:", font=f_label, fill=(120, 220, 150, 255))
        draw.text((rx + 36, ly + 196), f"+{amount:,} ₪", font=f_huge, fill=(0, 240, 140, 255))
        draw.text((rx + 36, ly + 248), "Шекели грабителя перешли жертве", font=f_label, fill=(100, 180, 130, 255))
    else:
        draw.text((rx + 36, ly + 168), "БАЛАНС В СОХРАННОСТИ:", font=f_label, fill=(100, 190, 240, 255))
        draw.text((rx + 36, ly + 196), "0 ₪ ПОТЕРЬ", font=f_huge, fill=(0, 230, 150, 255))
        draw.text((rx + 36, ly + 248), "Фольга успешно отразила нападение", font=f_label, fill=(90, 160, 180, 255))

    # 6. Bottom Banner
    draw.rounded_rectangle([48, 430, W - 48, 495], radius=10, fill=(18, 24, 34, 255), outline=(36, 46, 64, 255), width=1)
    if outcome == "success":
        bottom_txt = "Гоп-стоп прошел успешно. Анон обчищен."
    elif outcome == "pepperspray":
        bottom_txt = "Перцовый баллончик спас шекели и наказал нападающего!"
    else:
        bottom_txt = "Шапочка из фольги спасла баланс жертвы."
    draw.text((70, 452), bottom_txt, font=f_label, fill=(210, 225, 245, 255))
    draw.text((W - 240, 452), "/shop — экипироваться", font=f_badge, fill=(255, 215, 40, 255))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf
