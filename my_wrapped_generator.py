# -*- coding: utf-8 -*-
"""
my_wrapped_generator.py — Standalone Personalized "2ch Wrapped" Card Generator for DvachBot.
Produces high-resolution (1080x1080) personal analytics posters in dark cyberpunk style.
"""

import os
import io
import time
import json
import sqlite3
import contextlib
from typing import Dict, Any, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common.anon_identity import get_anon_id, generate_anon_name
from common.chart_lock import matplotlib_guard

THEME_BG = "#0b0f17"
THEME_CARD = "#131924"
THEME_BORDER = "#1f293d"

COLOR_CYAN = "#00f0ff"
COLOR_PINK = "#ff0055"
COLOR_GREEN = "#39d353"
COLOR_AMBER = "#ffaa00"
COLOR_PURPLE = "#a855f7"
COLOR_TEXT_MAIN = "#f1f5f9"
COLOR_TEXT_MUTED = "#94a3b8"

def connect_ro_db(db_path: str = "file:dvach_bot.db?mode=ro") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_user_wrapped_data(user_id: int) -> Dict[str, Any]:
    """Fetches user metrics for Wrapped generation."""
    with contextlib.closing(connect_ro_db()) as conn:
        c = conn.cursor()
        
        # 1. Total Posts & Character volume
        c.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(content)), 0) FROM Posts WHERE author_id = ?", (user_id,))
        p_row = c.fetchone()
        total_posts = (p_row[0] or 0) if p_row else 0
        total_chars = (p_row[1] or 0) if p_row else 0

        # 2. Favorite Board & Chronotype
        if total_posts == 0:
            fav_board = "-"
            chronotype = "Не определен"
            archetype = "Ньюфаг / Призрак"
        else:
            c.execute("""
                SELECT board_id, COUNT(*) as cnt
                FROM Posts WHERE author_id = ?
                GROUP BY board_id ORDER BY cnt DESC LIMIT 1
            """, (user_id,))
            b_row = c.fetchone()
            fav_board = b_row['board_id'] if b_row and b_row['board_id'] else "b"

            c.execute("""
                SELECT cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                       COUNT(*) as cnt
                FROM Posts WHERE author_id = ?
                GROUP BY h ORDER BY cnt DESC LIMIT 1
            """, (user_id,))
            h_row = c.fetchone()
            peak_hour = h_row['h'] if h_row and h_row['h'] is not None else 23

            if 0 <= peak_hour < 6:
                chronotype = f"Ночной Сыч ({peak_hour:02d}:00)"
                archetype = "Хронический Полуночный Шизоид"
            elif 6 <= peak_hour < 12:
                chronotype = f"Утренний Скуф ({peak_hour:02d}:00)"
                archetype = "Бодрый Утренний Эксперт"
            elif 12 <= peak_hour < 18:
                chronotype = f"Дневной Офисник ({peak_hour:02d}:00)"
                archetype = "Рабочий Щитпостер"
            else:
                chronotype = f"Вечерний Подпивас ({peak_hour:02d}:00)"
                archetype = "Главный Дуэлянт Тред-Перекатов"

        # 3. Financials
        c.execute("SELECT balance FROM Users WHERE user_id = ?", (user_id,))
        u_row = c.fetchone()
        balance = (u_row['balance'] if u_row and u_row['balance'] is not None else 0)

        c.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as earned,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spent
            FROM UserTransactions WHERE user_id = ?
        """, (user_id,))
        tx_row = c.fetchone()
        earned = (tx_row['earned'] if tx_row and tx_row['earned'] is not None else 0)
        spent = (tx_row['spent'] if tx_row and tx_row['spent'] is not None else 0)

        # 4. Top Interlocutors (Replies given/received)
        c.execute("""
            SELECT orig.author_id as partner, COUNT(*) as cnt
            FROM Posts repl
            JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
            WHERE repl.author_id = ? AND orig.author_id IS NOT NULL AND orig.author_id != ?
            GROUP BY partner ORDER BY cnt DESC LIMIT 1
        """, (user_id, user_id))
        part_row = c.fetchone()
        top_partner = generate_anon_name(part_row['partner']).split('(')[0] if part_row and part_row['partner'] is not None else "Никто (Одинокий Волк)"
        top_partner_cnt = (part_row['cnt'] or 0) if part_row else 0

        # 5. Degradation & Toxicity Score
        c.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN content LIKE '%хуй%' OR content LIKE '%бля%' OR content LIKE '%пизд%' OR content LIKE '%еба%' THEN 1 ELSE 0 END) as tox
            FROM Posts WHERE author_id = ?
        """, (user_id,))
        tox_row = c.fetchone()
        total_p = (tox_row['total'] or 0) if tox_row else 0
        tox_p = (tox_row['tox'] or 0) if tox_row else 0
        cringe_pct = min(100, max(5, int((tox_p / max(1, total_p)) * 100 * 1.5)))

    anon_name = generate_anon_name(user_id)
    return {
        "user_id": user_id,
        "anon_name": anon_name,
        "total_posts": total_posts,
        "total_chars": total_chars,
        "fav_board": fav_board,
        "chronotype": chronotype,
        "archetype": archetype,
        "balance": balance,
        "earned": earned,
        "spent": spent,
        "top_partner": top_partner,
        "top_partner_cnt": top_partner_cnt,
        "cringe_pct": cringe_pct
    }

def generate_my_wrapped_poster(user_id: int) -> io.BytesIO:
    """Renders a 1080x1350 Spotify-Wrapped style poster for the user."""
    data = fetch_user_wrapped_data(user_id)

    with matplotlib_guard():
        fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
        fig.patch.set_facecolor(THEME_BG)

        # Header Badge
        fig.text(0.5, 0.94, "ТГАЧ WRAPPED • ПЕРСОНАЛЬНЫЙ СРЕЗ", fontsize=18, fontweight='bold', color=COLOR_CYAN, ha='center')
        fig.text(0.5, 0.91, f"Личный цифровой паспорт анона {data['anon_name']}", fontsize=11, color=COLOR_TEXT_MUTED, ha='center')

        gs = fig.add_gridspec(3, 2, left=0.08, right=0.92, top=0.86, bottom=0.08, hspace=0.35, wspace=0.25)
        ax1 = fig.add_subplot(gs[0, 0]) # Archetype Card
        ax2 = fig.add_subplot(gs[0, 1]) # Activity & Volume
        ax3 = fig.add_subplot(gs[1, 0]) # Economy & Shekels
        ax4 = fig.add_subplot(gs[1, 1]) # Social & Best Frenemy
        ax5 = fig.add_subplot(gs[2, :])  # Degradation Progress Bar & Verdict

        # --- Card 1: Archetype ---
        ax1.set_facecolor(THEME_CARD)
        ax1.set_xticks([]); ax1.set_yticks([])
        ax1.text(0.5, 0.75, "ТВОЙ АРХЕТИП", fontsize=9, color=COLOR_AMBER, ha='center', fontweight='bold')
        ax1.text(0.5, 0.45, data['archetype'], fontsize=11, color=COLOR_TEXT_MAIN, ha='center', fontweight='bold', wrap=True)
        ax1.text(0.5, 0.18, f"Любимая доска: /{data['fav_board']}/", fontsize=9, color=COLOR_CYAN, ha='center')
        ax1.set_title("Архетип Личности", fontsize=10, color=COLOR_AMBER, fontweight='bold')

        # --- Card 2: Post Stats ---
        ax2.set_facecolor(THEME_CARD)
        ax2.set_xticks([]); ax2.set_yticks([])
        ax2.text(0.5, 0.75, "ОБЪЕМ ВЫСЕРОВ", fontsize=9, color=COLOR_GREEN, ha='center', fontweight='bold')
        ax2.text(0.5, 0.45, f"{int(data['total_posts']):,} постов", fontsize=16, color=COLOR_GREEN, ha='center', fontweight='bold')
        ax2.text(0.5, 0.18, f"Хронотип: {data['chronotype']}", fontsize=9, color=COLOR_TEXT_MUTED, ha='center')
        ax2.set_title("Активность", fontsize=10, color=COLOR_GREEN, fontweight='bold')

        # --- Card 3: Economy ---
        ax3.set_facecolor(THEME_CARD)
        ax3.set_xticks([]); ax3.set_yticks([])
        ax3.text(0.5, 0.75, "ФИНАНСОВЫЙ СТАТУС", fontsize=9, color=COLOR_AMBER, ha='center', fontweight='bold')
        ax3.text(0.5, 0.48, f"{int(data['balance'] or 0):,} ₪", fontsize=15, color=COLOR_AMBER, ha='center', fontweight='bold')
        ax3.text(0.5, 0.20, f"Оборот: +{int(data['earned'] or 0):,} / -{int(data['spent'] or 0):,} ₪", fontsize=8.5, color=COLOR_TEXT_MUTED, ha='center')
        ax3.set_title("Капитал", fontsize=10, color=COLOR_AMBER, fontweight='bold')

        # --- Card 4: Frenemy ---
        ax4.set_facecolor(THEME_CARD)
        ax4.set_xticks([]); ax4.set_yticks([])
        ax4.text(0.5, 0.75, "ГЛАВНЫЙ СПАРРИНГ-ПАРТНЕР", fontsize=9, color=COLOR_PINK, ha='center', fontweight='bold')
        ax4.text(0.5, 0.45, data['top_partner'], fontsize=11, color=COLOR_TEXT_MAIN, ha='center', fontweight='bold')
        ax4.text(0.5, 0.18, f"Взаимных реплаев: {int(data['top_partner_cnt'] or 0)}", fontsize=9, color=COLOR_PINK, ha='center')
        ax4.set_title("Социальный Контакт", fontsize=10, color=COLOR_PINK, fontweight='bold')

        # --- Card 5: Degradation Bar ---
        ax5.set_facecolor(THEME_CARD)
        ax5.set_xticks([]); ax5.set_yticks([])
        
        pct = data['cringe_pct']
        bar_color = COLOR_PINK if pct > 50 else COLOR_CYAN
        ax5.text(0.05, 0.70, "ШКАЛА ДЕГРАДАЦИИ И МАТОЕМКОСТИ:", fontsize=10, color=COLOR_TEXT_MAIN, fontweight='bold')
        ax5.text(0.95, 0.70, f"{pct}%", fontsize=12, color=bar_color, ha='right', fontweight='bold')

        # Progress bar rectangle
        rect_bg = mpatches.FancyBboxPatch((0.05, 0.35), 0.90, 0.18, boxstyle="round,pad=0.01", facecolor=THEME_BG, edgecolor=THEME_BORDER)
        ax5.add_patch(rect_bg)
        fill_width = max(0.04, 0.90 * (pct / 100.0))
        rect_fill = mpatches.FancyBboxPatch((0.05, 0.35), fill_width, 0.18, boxstyle="round,pad=0.01", facecolor=bar_color, edgecolor='none')
        ax5.add_patch(rect_fill)

        verdict_text = "ДИАГНОЗ ИИ: Базированный анон с устойчивой психикой." if pct < 35 else (
            "ДИАГНОЗ ИИ: Острый синдром полуночного щитпостинга с периодическими обострениями." if pct < 65 else
            "ДИАГНОЗ ИИ: Терминальная стадия двачера. Рекомендуется принудительный аминазин."
        )
        ax5.text(0.5, 0.12, verdict_text, fontsize=9.5, color=COLOR_TEXT_MUTED, ha='center', style='italic')
        ax5.set_title("Итоговый Вердикт", fontsize=10, color=COLOR_PURPLE, fontweight='bold')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME_BG, edgecolor='none', bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        return buf
