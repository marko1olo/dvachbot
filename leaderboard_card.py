# -*- coding: utf-8 -*-
"""
leaderboard_card.py — Next-Gen 960x540 Leaderboard Card Generator for ТГАЧ
Generates high-resolution cyber-imageboard leaderboard cards (Rich list, Shitposters, Karma)
with podiums, progress bars, caller highlighting, and in-memory cache.
"""

import io
import time
import sqlite3
import datetime
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont

from stats_generator import connect_stats_db
from common.anon_identity import get_anon_id, generate_anon_name

MAX_LEADERBOARD_CACHE_SIZE = 30
LEADERBOARD_CACHE: OrderedDict[str, Tuple[float, io.BytesIO, str]] = OrderedDict()
CACHE_TTL = 60.0  # 60 seconds cache per (board_id, mode)


@dataclass
class LeaderboardEntry:
    user_id: int
    rank: int
    anon_tag: str
    custom_prefix: Optional[str]
    value: int
    is_caller: bool


@dataclass
class LeaderboardData:
    board_id: str
    mode: str
    mode_title: str
    unit: str
    entries: List[LeaderboardEntry]
    caller_id: int
    caller_rank: int
    caller_value: int
    total_users: int
    total_metric: int


def fetch_leaderboard_data(board_id: str, mode: str = "balance", caller_id: int = 0) -> LeaderboardData:
    conn = connect_stats_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM Users WHERE board_id = ?", (board_id,))
        row = cursor.fetchone()
        total_users = row[0] if row and row[0] else 1

        entries: List[LeaderboardEntry] = []
        caller_rank = 0
        caller_value = 0
        total_metric = 0

        if mode == "posts":
            mode_title = "ТОП ШИТПОСТЕРОВ"
            unit = "постов"

            cursor.execute(
                """SELECT p.author_id, COUNT(*) as cnt, MAX(u.custom_prefix) as prefix
                   FROM Posts p
                   LEFT JOIN Users u ON p.author_id = u.user_id AND p.board_id = u.board_id
                   WHERE p.board_id = ? AND p.author_id > 0
                   GROUP BY p.author_id
                   ORDER BY cnt DESC LIMIT 10""",
                (board_id,)
            )
            rows = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM Posts WHERE board_id = ? AND author_id > 0", (board_id,))
            tot_row = cursor.fetchone()
            total_metric = tot_row[0] if tot_row and tot_row[0] else 0

            if caller_id > 0:
                cursor.execute(
                    """SELECT COUNT(*) + 1 FROM (
                           SELECT author_id, COUNT(*) as cnt FROM Posts
                           WHERE board_id = ? AND author_id > 0
                           GROUP BY author_id
                           HAVING cnt > (SELECT COUNT(*) FROM Posts WHERE board_id = ? AND author_id = ?)
                       )""",
                    (board_id, board_id, caller_id)
                )
                cr_row = cursor.fetchone()
                caller_rank = cr_row[0] if cr_row else 0

                cursor.execute("SELECT COUNT(*) FROM Posts WHERE board_id = ? AND author_id = ?", (board_id, caller_id))
                cv_row = cursor.fetchone()
                caller_value = cv_row[0] if cv_row else 0

        elif mode == "reactions":
            mode_title = "ТОП ПО РЕАКЦИЯМ"
            unit = "реакций"

            cursor.execute(
                """SELECT user_id, COALESCE(reaction_reward_counter, 0) as rx, custom_prefix
                   FROM Users
                   WHERE board_id = ? AND COALESCE(reaction_reward_counter, 0) > 0
                   ORDER BY rx DESC LIMIT 10""",
                (board_id,)
            )
            rows = cursor.fetchall()

            cursor.execute("SELECT SUM(COALESCE(reaction_reward_counter, 0)) FROM Users WHERE board_id = ?", (board_id,))
            tot_row = cursor.fetchone()
            total_metric = tot_row[0] if tot_row and tot_row[0] else 0

            if caller_id > 0:
                cursor.execute(
                    """SELECT COUNT(*) + 1 FROM Users
                       WHERE board_id = ? AND COALESCE(reaction_reward_counter, 0) > (
                           SELECT COALESCE(reaction_reward_counter, 0) FROM Users WHERE board_id = ? AND user_id = ?
                       )""",
                    (board_id, board_id, caller_id)
                )
                cr_row = cursor.fetchone()
                caller_rank = cr_row[0] if cr_row else 0

                cursor.execute("SELECT COALESCE(reaction_reward_counter, 0) FROM Users WHERE board_id = ? AND user_id = ?", (board_id, caller_id))
                cv_row = cursor.fetchone()
                caller_value = cv_row[0] if cv_row else 0

        elif mode in ("music", "tracks", "говноеды", "говноед"):
            mode = "music"
            mode_title = "ТОП ГОВНОЕДОВ (МУЗЫКА)"
            unit = "зашкваров"

            cursor.execute(
                """SELECT m.user_id, COUNT(*) as cnt, MAX(u.custom_prefix) as prefix
                   FROM MusicRoasts m
                   LEFT JOIN Users u ON m.user_id = u.user_id AND m.board_id = u.board_id
                   WHERE m.board_id = ? AND m.user_id > 0
                   GROUP BY m.user_id
                   ORDER BY cnt DESC LIMIT 10""",
                (board_id,)
            )
            rows = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM MusicRoasts WHERE board_id = ?", (board_id,))
            tot_row = cursor.fetchone()
            total_metric = tot_row[0] if tot_row and tot_row[0] else 0

            if caller_id > 0:
                cursor.execute(
                    """SELECT COUNT(*) + 1 FROM (
                           SELECT user_id, COUNT(*) as cnt FROM MusicRoasts
                           WHERE board_id = ? AND user_id > 0
                           GROUP BY user_id
                           HAVING cnt > (SELECT COUNT(*) FROM MusicRoasts WHERE board_id = ? AND user_id = ?)
                       )""",
                    (board_id, board_id, caller_id)
                )
                cr_row = cursor.fetchone()
                caller_rank = cr_row[0] if cr_row else 0

                cursor.execute("SELECT COUNT(*) FROM MusicRoasts WHERE board_id = ? AND user_id = ?", (board_id, caller_id))
                cv_row = cursor.fetchone()
                caller_value = cv_row[0] if cv_row else 0

        else: # balance (default)
            mode = "balance"
            mode_title = "ТОП БОГАЧЕЙ"
            unit = "RUB"

            cursor.execute(
                """SELECT user_id, SUM(balance) as bal, MAX(custom_prefix) as prefix
                   FROM Users WHERE board_id = ?
                   GROUP BY user_id HAVING bal > 0
                   ORDER BY bal DESC LIMIT 10""",
                (board_id,)
            )
            rows = cursor.fetchall()

            cursor.execute("SELECT SUM(balance) FROM Users WHERE board_id = ?", (board_id,))
            tot_row = cursor.fetchone()
            total_metric = int(tot_row[0]) if tot_row and tot_row[0] else 0

            if caller_id > 0:
                cursor.execute(
                    """SELECT COUNT(*) + 1 FROM (
                           SELECT user_id, SUM(balance) as bal FROM Users
                           WHERE board_id = ?
                           GROUP BY user_id
                           HAVING bal > (SELECT SUM(balance) FROM Users WHERE board_id = ? AND user_id = ?)
                       )""",
                    (board_id, board_id, caller_id)
                )
                cr_row = cursor.fetchone()
                caller_rank = cr_row[0] if cr_row else 0

                cursor.execute("SELECT SUM(balance) FROM Users WHERE board_id = ? AND user_id = ?", (board_id, caller_id))
                cv_row = cursor.fetchone()
                caller_value = int(cv_row[0]) if cv_row and cv_row[0] else 0

        for i, row in enumerate(rows):
            uid = row[0]
            val = int(row[1])
            pfx = row[2] if len(row) > 2 and row[2] else None
            is_call = (uid == caller_id)
            anon_tag = f"Anon [{get_anon_id(uid, 'en')}]" if board_id == "int" else f"Анон [{get_anon_id(uid)}]"
            entries.append(LeaderboardEntry(
                user_id=uid,
                rank=i + 1,
                anon_tag=anon_tag,
                custom_prefix=pfx,
                value=val,
                is_caller=is_call
            ))

        return LeaderboardData(
            board_id=board_id,
            mode=mode,
            mode_title=mode_title,
            unit=unit,
            entries=entries,
            caller_id=caller_id,
            caller_rank=caller_rank,
            caller_value=caller_value,
            total_users=total_users,
            total_metric=total_metric
        )
    finally:
        conn.close()


def draw_leaderboard_card(data: LeaderboardData) -> io.BytesIO:
    W, H = 960, 540

    # Color Palette per mode
    if data.mode == "balance":
        bg_top = (15, 17, 24)
        bg_bot = (10, 12, 18)
        accent_color = (250, 180, 20)      # Rich Amber Gold
        accent_glow = (250, 180, 20, 30)
        card_fill = (22, 26, 36)
        card_stroke = (45, 54, 75)
        badge_bg = (40, 32, 12)
        badge_border = (180, 130, 20)
    elif data.mode == "posts":
        bg_top = (12, 18, 28)
        bg_bot = (8, 12, 20)
        accent_color = (20, 200, 240)      # Cyber Cyan
        accent_glow = (20, 200, 240, 30)
        card_fill = (18, 25, 42)
        card_stroke = (35, 50, 80)
        badge_bg = (12, 35, 48)
        badge_border = (20, 160, 200)
    elif data.mode == "music":
        bg_top = (28, 16, 12)
        bg_bot = (16, 10, 8)
        accent_color = (255, 90, 30)       # Toxic Flame Orange
        accent_glow = (255, 90, 30, 35)
        card_fill = (38, 22, 16)
        card_stroke = (75, 42, 28)
        badge_bg = (48, 24, 12)
        badge_border = (210, 85, 20)
    else: # reactions
        bg_top = (22, 14, 26)
        bg_bot = (14, 8, 18)
        accent_color = (245, 80, 160)      # Neon Magenta
        accent_glow = (245, 80, 160, 30)
        card_fill = (28, 20, 36)
        card_stroke = (65, 42, 80)
        badge_bg = (45, 18, 40)
        badge_border = (190, 50, 120)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Vertical gradient background
    for y in range(H):
        r = int(bg_top[0] + (bg_bot[0] - bg_top[0]) * (y / H))
        g = int(bg_top[1] + (bg_bot[1] - bg_top[1]) * (y / H))
        b = int(bg_top[2] + (bg_bot[2] - bg_top[2]) * (y / H))
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Fonts
    def get_font(name: str, size: int):
        paths = [
            f"C:/Windows/Fonts/{name}.ttf",
            f"C:/Windows/Fonts/{name}",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf"
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    f_head_title = get_font("segoeuib", 20)
    f_head_tag = get_font("segoeuib", 13)
    f_head_meta = get_font("segoeui", 12)
    f_pod_rank = get_font("segoeuib", 12)
    f_pod_name = get_font("segoeuib", 16)
    f_pod_val = get_font("segoeuib", 20)
    f_badge = get_font("segoeuib", 10)
    f_row_rank = get_font("segoeuib", 12)
    f_row_name = get_font("segoeuib", 13)
    f_row_val = get_font("segoeuib", 13)
    f_footer = get_font("segoeui", 11)

    # 1. Header Bar
    tag_str = f"/{data.board_id}/ • ТГАЧ"
    tag_w = int(draw.textlength(tag_str, font=f_head_tag)) + 24
    draw.rounded_rectangle([28, 20, 28 + tag_w, 48], radius=8, fill=badge_bg, outline=badge_border, width=1)
    draw.text((40, 25), tag_str, font=f_head_tag, fill=accent_color)

    title_x = 28 + tag_w + 16
    draw.text((title_x, 23), data.mode_title, font=f_head_title, fill=(255, 255, 255, 255))

    now_str = datetime.datetime.now().strftime("%d.%m • %H:%M")
    tot_str = f"Всего в банке: {data.total_metric:,} {data.unit}"
    draw.text((W - 28 - int(draw.textlength(tot_str, font=f_head_meta)), 20), tot_str, font=f_head_meta, fill=(210, 220, 235, 255))
    draw.text((W - 28 - int(draw.textlength(now_str, font=f_head_meta)), 36), now_str, font=f_head_meta, fill=(130, 145, 165, 255))

    draw.line([(28, 58), (W - 28, 58)], fill=(45, 55, 75, 255), width=1)

    # 2. Podium Block (Top 3 Cards Side by Side)
    # Layout: Slot 0 = #2 Silver, Slot 1 = #1 Gold (Elevated Center), Slot 2 = #3 Bronze
    podium_y = 70
    card_w = 280
    card_h = 138
    gap = 25
    start_x = 28

    slot_to_rank_idx = {0: 1, 1: 0, 2: 2}

    for slot in range(3):
        entry_idx = slot_to_rank_idx[slot]
        cx = start_x + slot * (card_w + gap)
        cy = podium_y

        if entry_idx < len(data.entries):
            e = data.entries[entry_idx]
            is_first = (entry_idx == 0)

            if is_first:
                p_border = (255, 215, 0, 255)
                p_tag_bg = (60, 48, 12, 255)
                p_tag_border = (255, 215, 0, 255)
                p_tag_text = "1 МЕСТО • ЧЕМПИОН"
            elif entry_idx == 1:
                p_border = (195, 210, 225, 255)
                p_tag_bg = (35, 42, 54, 255)
                p_tag_border = (195, 210, 225, 255)
                p_tag_text = "2 МЕСТО"
            else:
                p_border = (225, 145, 75, 255)
                p_tag_bg = (50, 30, 16, 255)
                p_tag_border = (225, 145, 75, 255)
                p_tag_text = "3 МЕСТО"

            # Draw card
            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=12, fill=card_fill, outline=p_border if is_first else card_stroke, width=2 if is_first else 1)

            # Top Badge Pill
            draw.rounded_rectangle([cx + 14, cy + 12, cx + card_w - 14, cy + 34], radius=6, fill=p_tag_bg, outline=p_tag_border, width=1)
            draw.text((cx + 24, cy + 15), p_tag_text, font=f_pod_rank, fill=p_border)

            # Anon Tag
            draw.text((cx + 18, cy + 46), e.anon_tag, font=f_pod_name, fill=(255, 255, 255, 255))
            if e.custom_prefix:
                pfx_clean = e.custom_prefix[:14]
                pfx_w = int(draw.textlength(pfx_clean, font=f_badge)) + 14
                pfx_x = cx + 18 + int(draw.textlength(e.anon_tag, font=f_pod_name)) + 8
                draw.rounded_rectangle([pfx_x, cy + 47, pfx_x + pfx_w, cy + 63], radius=4, fill=(255, 255, 255, 20), outline=(255, 255, 255, 40), width=1)
                draw.text((pfx_x + 7, cy + 49), pfx_clean, font=f_badge, fill=accent_color)

            # Value & Unit
            val_str = f"{e.value:,} {data.unit}"
            draw.text((cx + 18, cy + 74), val_str, font=f_pod_val, fill=p_border if is_first else (235, 242, 255, 255))

            # Progress Mini Bar
            max_val = max(1, data.entries[0].value)
            bar_track_w = card_w - 36
            bar_fill_w = max(8, int(bar_track_w * (e.value / max_val)))
            draw.rounded_rectangle([cx + 18, cy + 112, cx + 18 + bar_track_w, cy + 118], radius=3, fill=(35, 42, 58, 255))
            draw.rounded_rectangle([cx + 18, cy + 112, cx + 18 + bar_fill_w, cy + 118], radius=3, fill=p_border)
        else:
            # Empty slot
            draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=12, fill=card_fill, outline=(35, 42, 58, 255), width=1)
            draw.text((cx + 20, cy + 55), "Свободное место", font=f_head_meta, fill=(90, 105, 125, 255))

    # 3. Places #4 to #10 in 2 Columns
    list_y = 226
    col_w = 440
    row_h = 36
    max_val = max(1, data.entries[0].value) if data.entries else 1

    remaining_entries = data.entries[3:10] # #4 to #10
    for i, e in enumerate(remaining_entries):
        col = 0 if i < 4 else 1
        row = i if col == 0 else (i - 4)
        rx = 28 if col == 0 else (W - 28 - col_w)
        ry = list_y + row * (row_h + 8)

        is_me = e.is_caller
        row_stroke = accent_color if is_me else card_stroke
        row_fill = badge_bg if is_me else card_fill

        draw.rounded_rectangle([rx, ry, rx + col_w, ry + row_h], radius=8, fill=row_fill, outline=row_stroke, width=1.5 if is_me else 1)

        # Rank Badge Box
        draw.rounded_rectangle([rx + 8, ry + 7, rx + 36, ry + 29], radius=5, fill=(35, 44, 64, 255))
        draw.text((rx + 14, ry + 10), f"#{e.rank}", font=f_row_rank, fill=(210, 225, 245, 255))

        # Anon Name + Prefix
        name_str = e.anon_tag
        if is_me:
            name_str += " (ТЫ)"
        draw.text((rx + 46, ry + 10), name_str, font=f_row_name, fill=accent_color if is_me else (255, 255, 255, 255))

        if e.custom_prefix:
            pfx_clean = e.custom_prefix[:10]
            pfx_w = int(draw.textlength(pfx_clean, font=f_badge)) + 12
            pfx_x = rx + 46 + int(draw.textlength(name_str, font=f_row_name)) + 6
            if pfx_x + pfx_w < rx + col_w - 120:
                draw.rounded_rectangle([pfx_x, ry + 9, pfx_x + pfx_w, ry + 25], radius=4, fill=(255, 255, 255, 18))
                draw.text((pfx_x + 6, ry + 11), pfx_clean, font=f_badge, fill=accent_color)

        # Metric Value
        v_str = f"{e.value:,} {data.unit}"
        vw = int(draw.textlength(v_str, font=f_row_val))
        draw.text((rx + col_w - 14 - vw, ry + 10), v_str, font=f_row_val, fill=(225, 235, 250, 255))

        # Thin visual line
        prog_w = int((col_w - 60 - vw) * (e.value / max_val))
        draw.line([(rx + 46, ry + 30), (rx + 46 + max(6, prog_w), ry + 30)], fill=accent_color if is_me else (60, 75, 100, 255), width=2)

    # 4. Footer Bar
    foot_y = H - 42
    draw.line([(28, foot_y), (W - 28, foot_y)], fill=(45, 55, 75, 255), width=1)

    caller_status = f"Твоё место: #{data.caller_rank} ({data.caller_value:,} {data.unit})" if data.caller_rank > 0 else "Ты ещё не в топе"
    draw.text((28, foot_y + 12), f"Всего анонов: {data.total_users:,}  •  {caller_status}", font=f_footer, fill=(160, 175, 195, 255))
    draw.text((W - 140, foot_y + 12), "tgach.top • /top", font=f_footer, fill=accent_color)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


def format_leaderboard_text(data: LeaderboardData) -> str:
    medals = ["🥇", "🥈", "🥉"]
    header_icon = "💩" if data.mode == "music" else "🏆"
    lines = [
        f"{header_icon} <b>{data.mode_title} /{data.board_id}/</b>",
        f"<code>{'—'*28}</code>"
    ]

    for e in data.entries[:10]:
        medal = medals[e.rank - 1] if e.rank <= 3 else f"<b>{e.rank}.</b>"
        pfx = f" [{e.custom_prefix}]" if e.custom_prefix else ""
        you = " <b>← ТЫ</b>" if e.is_caller else ""
        lines.append(f"{medal} <code>{e.anon_tag}</code>{pfx} — <b>{e.value:,} {data.unit}</b>{you}")

    lines.append(f"<code>{'—'*28}</code>")
    if data.caller_rank > 0:
        lines.append(f"👤 <b>Твой результат:</b> Ранг #{data.caller_rank} (<code>{data.caller_value:,} {data.unit}</code>)")
    else:
        lines.append("👤 <i>Проявляй активность на борде, чтобы попасть в топ!</i>")

    return "\n".join(lines)


def generate_leaderboard_payload(board_id: str, mode: str = "balance", caller_id: int = 0) -> Tuple[io.BytesIO, str]:
    """
    Returns (photo_buffer, html_caption) with 60s in-memory caching and bounded LRU cache (maxsize=30).
    """
    cache_key = f"{board_id}_{mode}_{caller_id}"
    now = time.time()

    cached = LEADERBOARD_CACHE.get(cache_key)
    if cached:
        if now - cached[0] < CACHE_TTL:
            LEADERBOARD_CACHE.move_to_end(cache_key)
            buf = io.BytesIO(cached[1].getvalue())
            return buf, cached[2]
        else:
            old_val = LEADERBOARD_CACHE.pop(cache_key, None)
            if old_val and old_val[1]:
                try:
                    old_val[1].close()
                except Exception:
                    pass

    data = fetch_leaderboard_data(board_id=board_id, mode=mode, caller_id=caller_id)
    buf = draw_leaderboard_card(data)
    text = format_leaderboard_text(data)

    if cache_key in LEADERBOARD_CACHE:
        old_val = LEADERBOARD_CACHE.pop(cache_key, None)
        if old_val and old_val[1]:
            try:
                old_val[1].close()
            except Exception:
                pass

    while len(LEADERBOARD_CACHE) >= MAX_LEADERBOARD_CACHE_SIZE:
        _, old_val = LEADERBOARD_CACHE.popitem(last=False)
        if old_val and old_val[1]:
            try:
                old_val[1].close()
            except Exception:
                pass

    LEADERBOARD_CACHE[cache_key] = (now, buf, text)
    return io.BytesIO(buf.getvalue()), text
