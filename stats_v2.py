# -*- coding: utf-8 -*-
"""
stats_v2.py — Next-Gen Standalone Analytics Engine & Poster Renderer for DvachBot.
100% standalone, fully isolated from stats_generator.py and periodic_publisher.py.
Supports Instant ASCII Sparklines, HD Theme Posters (Economy, PvP, Drama, Memetics),
and safe read-only WAL database querying.
"""

import os
import io
import time
import math
import json
import sqlite3
import contextlib
import warnings
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional, Any

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd

from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
warnings.filterwarnings("ignore", message=".*Glyph.*")

from common.anon_identity import get_anon_id, generate_anon_name
from common.chart_lock import matplotlib_guard

# -----------------------------------------------------------------------------
# Dark Cyberpunk Styling Configuration
# -----------------------------------------------------------------------------
THEME_BG = "#0b0f17"
THEME_CARD = "#131924"
THEME_BORDER = "#1f293d"
THEME_GRID = "#1a2333"

COLOR_CYAN = "#00f0ff"
COLOR_PINK = "#ff0055"
COLOR_GREEN = "#39d353"
COLOR_AMBER = "#ffaa00"
COLOR_PURPLE = "#a855f7"
COLOR_BLUE = "#38bdf8"
COLOR_TEXT_MAIN = "#f1f5f9"
COLOR_TEXT_MUTED = "#94a3b8"

SNS_RC_V2 = {
    "axes.facecolor": THEME_CARD,
    "figure.facecolor": THEME_BG,
    "text.color": COLOR_TEXT_MAIN,
    "axes.labelcolor": COLOR_TEXT_MUTED,
    "xtick.color": COLOR_TEXT_MUTED,
    "ytick.color": COLOR_TEXT_MUTED,
    "grid.color": THEME_GRID,
    "grid.linestyle": "--",
    "grid.alpha": 0.6,
    "font.family": "sans-serif"
}

SPARK_BARS = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

def connect_ro_db(db_path: str = "file:dvach_bot.db?mode=ro", timeout: float = 15.0) -> sqlite3.Connection:
    """Connects to SQLite in read-only WAL mode safely."""
    conn = sqlite3.connect(db_path, uri=True, timeout=timeout)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
    except Exception:
        pass
    return conn

def apply_theme_v2():
    plt.style.use('dark_background')
    sns.set_theme(style="darkgrid", rc=SNS_RC_V2)

def make_sparkline(numbers: List[float], length: int = 12) -> str:
    """Converts a series of numbers into an 8-level ASCII sparkline."""
    if not numbers:
        return " ▂▃▅▆▇"
    if len(numbers) > length:
        chunk_size = len(numbers) / length
        condensed = [np.mean(numbers[int(i * chunk_size):int((i + 1) * chunk_size)]) for i in range(length)]
    else:
        condensed = numbers

    mn, mx = min(condensed), max(condensed)
    if mx == mn:
        return SPARK_BARS[3] * len(condensed)
    
    spark = ""
    for val in condensed:
        idx = int((val - mn) / (mx - mn) * (len(SPARK_BARS) - 1))
        idx = max(0, min(len(SPARK_BARS) - 1, idx))
        spark += SPARK_BARS[idx]
    return spark

# -----------------------------------------------------------------------------
# 1. Instant Snapshot Text Generator (< 50ms)
# -----------------------------------------------------------------------------
def generate_instant_snapshot_text(board_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Generates a lightning-fast rich text snapshot of current imageboard vitals.
    Runs in < 40ms without heavy rendering.
    """
    now_ts = time.time()
    day_ago = now_ts - 86400
    week_ago = now_ts - 7 * 86400

    with contextlib.closing(connect_ro_db()) as conn:
        c = conn.cursor()
        
        b_filter = "AND board_id = ?" if board_id else ""
        params_24h = (day_ago, board_id) if board_id else (day_ago,)
        params_7d = (week_ago, board_id) if board_id else (week_ago,)

        c.execute(f"SELECT COUNT(*), COUNT(DISTINCT author_id) FROM Posts WHERE timestamp > ? {b_filter}", params_24h)
        row_24h = c.fetchone()
        posts_24h = row_24h[0] if row_24h else 0
        users_24h = row_24h[1] if row_24h else 0

        c.execute(f"SELECT COUNT(*), COUNT(DISTINCT author_id) FROM Posts WHERE timestamp > ? {b_filter}", params_7d)
        row_7d = c.fetchone()
        posts_7d = row_7d[0] if row_7d else 0
        users_7d = row_7d[1] if row_7d else 0

        # Hourly breakdown for 24h sparkline
        c.execute(f"""
            SELECT cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                   COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ? {b_filter}
            GROUP BY h ORDER BY h
        """, params_24h)
        hour_counts = {r['h']: r['cnt'] for r in c.fetchall()}
        hourly_series = [hour_counts.get(h, 0) for h in range(24)]
        sparkline_str = make_sparkline(hourly_series, length=24)

        # Top 3 Boards
        c.execute("SELECT board_id, COUNT(*) as cnt FROM Posts WHERE timestamp > ? GROUP BY board_id ORDER BY cnt DESC LIMIT 3", (day_ago,))
        top_boards = [(r['board_id'], r['cnt']) for r in c.fetchall()]

        # Economy Pulse
        c.execute("SELECT COUNT(*), COALESCE(SUM(ABS(amount)), 0) FROM UserTransactions WHERE timestamp > ?", (day_ago,))
        tx_row = c.fetchone()
        tx_count = tx_row[0] if tx_row else 0
        tx_volume = tx_row[1] if tx_row else 0

        # Top Viral Meme
        c.execute("SELECT file_unique_id, times FROM MediaReposts ORDER BY times DESC LIMIT 1")
        top_repost = c.fetchone()
        top_meme_times = top_repost['times'] if top_repost else 0

    scope_name = f"/{board_id}/" if board_id else "ВСЕ ДОСКИ"
    now_msk = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M MSK")

    boards_summary = " • ".join([f"<b>/{b}/</b>: {cnt}" for b, cnt in top_boards]) or "данных нет"

    text = (
        f"📊 <b>ДВАЧ-АНАЛИТИКА V2 • ПУЛЬС БОРДЫ</b>\n"
        f"⚡ <i>Срез: {scope_name} | {now_msk}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Активных анонов (DAU):</b> <code>{users_24h:,}</code> <i>(WAU: {users_7d:,})</i>\n"
        f"💬 <b>Высеров за 24ч:</b> <code>{posts_24h:,}</code> постов <i>(За 7д: {posts_7d:,})</i>\n"
        f"⏱️ <b>Средний темп:</b> <code>{round(posts_24h / 24.0, 1)}</code> постов/час\n\n"
        f"📈 <b>Циркадный ритм (24 часа):</b>\n"
        f"<code>[{sparkline_str}]</code> <i>(Пик: {max(hourly_series or [0])} пст/ч)</i>\n\n"
        f"🏆 <b>Топ досок за 24ч:</b> {boards_summary}\n"
        f"💰 <b>Оборот шекелей:</b> <code>{int(tx_volume):,} ₪</code> <i>({tx_count} транзакций)</i>\n"
        f"👑 <b>Главный баян недели:</b> <code>x{top_meme_times}</code> форсов\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <i>Выбери категорию ниже для генерации HD-постера или открой WebApp:</i>"
    )

    data_payload = {
        "posts_24h": posts_24h,
        "users_24h": users_24h,
        "posts_7d": posts_7d,
        "users_7d": users_7d,
        "hourly_series": hourly_series,
        "top_boards": top_boards,
        "tx_volume": tx_volume,
    }
    return text, data_payload


# -----------------------------------------------------------------------------
# 2. HD Poster 1: Economy, Casino & Crime Radar (1200x675)
# -----------------------------------------------------------------------------
def generate_economy_heists_poster() -> io.BytesIO:
    """Generates a 1200x675 dark-neon poster for Economy, Heists and Casino."""
    with matplotlib_guard():
        apply_theme_v2()
        fig = plt.figure(figsize=(12, 6.75), dpi=100)
        fig.patch.set_facecolor(THEME_BG)

        fig.text(0.05, 0.94, "ТГАЧ ЭКОНОМИКА & КРИМИНАЛ • ТЕНЕВОЙ БАРОМЕТР", fontsize=18, fontweight='bold', color=COLOR_AMBER)
        fig.text(0.05, 0.905, "Аналитика грабежей (/rob), казино, скорости обращения шекелей и снайпинга аирдропов (30 дней)", fontsize=10, color=COLOR_TEXT_MUTED)

        gs = fig.add_gridspec(2, 3, left=0.05, right=0.95, top=0.86, bottom=0.08, hspace=0.35, wspace=0.25)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[0, 2])
        ax4 = fig.add_subplot(gs[1, 0:2])
        ax5 = fig.add_subplot(gs[1, 2])

        with contextlib.closing(connect_ro_db()) as conn:
            c = conn.cursor()

            # 1. Top Robbers or Top Earners Fallback
            c.execute("""
                SELECT user_id, 
                       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as stolen
                FROM UserTransactions
                WHERE category = 'rob' OR description LIKE '%ограбл%' OR description LIKE '%пырнул%'
                GROUP BY user_id
                ORDER BY stolen DESC LIMIT 6
            """)
            rob_data = c.fetchall()
            if not rob_data or all((r['stolen'] or 0) == 0 for r in rob_data):
                # Fallback: Top Transaction Volume Users
                c.execute("""
                    SELECT user_id, SUM(ABS(amount)) as volume
                    FROM UserTransactions
                    GROUP BY user_id
                    ORDER BY volume DESC LIMIT 6
                """)
                top_tx = c.fetchall()
                if top_tx:
                    names = [generate_anon_name(r['user_id']).split('(')[0][:14] for r in top_tx]
                    vol_vals = [(r['volume'] or 0) for r in top_tx]
                    names.reverse(); vol_vals.reverse()
                    bars = ax1.barh(names, vol_vals, color=COLOR_AMBER, edgecolor=THEME_BG, height=0.6)
                    for b, v in zip(bars, vol_vals):
                        ax1.text(b.get_width() + max(vol_vals)*0.02, b.get_y() + b.get_height()/2, f"{int(v):,} ₪", va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                    ax1.set_xlim(0, max(max(vol_vals or [1]) * 1.3, 1))
                    ax1.set_title("Топ-6 Трейдеров Борды (Объем транзакций)", fontsize=11, fontweight='bold', color=COLOR_AMBER)
                else:
                    ax1.text(0.5, 0.5, "Данных по транзакциям пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=10)
                    ax1.set_xticks([]); ax1.set_yticks([])
                    ax1.set_title("Топ-6 Форточников Борды (/rob)", fontsize=11, fontweight='bold', color=COLOR_PINK)
            else:
                names = [generate_anon_name(r['user_id']).split('(')[0][:14] for r in rob_data]
                stolen_vals = [(r['stolen'] or 0) for r in rob_data]
                names.reverse(); stolen_vals.reverse()
                bars = ax1.barh(names, stolen_vals, color=COLOR_PINK, edgecolor=THEME_BG, height=0.6)
                for b, v in zip(bars, stolen_vals):
                    ax1.text(b.get_width() + max(stolen_vals)*0.02, b.get_y() + b.get_height()/2, f"{int(v):,} ₪", va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax1.set_xlim(0, max(max(stolen_vals or [1]) * 1.3, 1))
                ax1.set_title("Топ-6 Форточников Борды (/rob)", fontsize=11, fontweight='bold', color=COLOR_PINK)

            # 2. Casino RTP
            c.execute("""
                SELECT 
                    SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as bets,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as wins
                FROM UserTransactions
                WHERE category = 'casino' OR description LIKE '%казино%' OR description LIKE '%слоты%'
            """)
            cas_row = c.fetchone()
            bets = (cas_row['bets'] if cas_row and cas_row['bets'] is not None else 0)
            wins = (cas_row['wins'] if cas_row and cas_row['wins'] is not None else 0)
            rake = max(0, bets - wins)
            
            if bets == 0 and wins == 0:
                ax2.text(0.5, 0.5, "Ставок в казино пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax2.set_xticks([]); ax2.set_yticks([])
                ax2.set_title("Баланс Казино & RTP", fontsize=11, fontweight='bold', color=COLOR_GREEN)
            else:
                slices = [wins, rake]
                if sum(slices) == 0:
                    slices = [1, 0]
                ax2.pie(slices, labels=["Выигрыши анонов", "Казна Абу (Рейк)"], colors=[COLOR_GREEN, COLOR_PINK],
                        autopct='%1.1f%%', startangle=140, wedgeprops=dict(width=0.45, edgecolor=THEME_BG, linewidth=2),
                        textprops=dict(color=COLOR_TEXT_MAIN, fontsize=8, fontweight='bold'))
                actual_rtp = round((wins / max(1, bets)) * 100, 1)
                ax2.text(0, 0, f"RTP\n{actual_rtp}%", ha='center', va='center', fontsize=11, fontweight='bold', color=COLOR_AMBER)
                ax2.set_title("Баланс Казино & RTP", fontsize=11, fontweight='bold', color=COLOR_GREEN)

            # 3. Drop Sniping
            c.execute("""
                SELECT ROUND(claimed_at - created_at, 1) as sec
                FROM MoneyDrops
                WHERE status = 'claimed' AND claimed_at IS NOT NULL
                ORDER BY created_at DESC LIMIT 100
            """)
            drop_latencies = [max(0.1, min(60.0, r['sec'])) for r in c.fetchall() if r['sec'] is not None]
            if drop_latencies:
                sns.histplot(drop_latencies, bins=15, color=COLOR_CYAN, ax=ax3, kde=True, edgecolor=THEME_BG)
                med_lat = np.median(drop_latencies)
                ax3.axvline(med_lat, color=COLOR_PINK, linestyle='--', linewidth=1.5, label=f"Медиана: {med_lat:.1f}с")
                ax3.set_title("Скорость перехвата чеков (/drop)", fontsize=11, fontweight='bold', color=COLOR_CYAN)
                ax3.set_xlabel("Секунды до клейма", fontsize=8)
                ax3.legend(fontsize=8, loc='upper right')
            else:
                ax3.text(0.5, 0.5, "Чеков пока не сброшено", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax3.set_xticks([]); ax3.set_yticks([])
                ax3.set_title("Скорость перехвата чеков (/drop)", fontsize=11, fontweight='bold', color=COLOR_CYAN)

            # 4. Wealth Deciles
            c.execute("SELECT balance FROM Users WHERE balance >= 0 ORDER BY balance ASC")
            balances = [r['balance'] for r in c.fetchall() if r['balance'] is not None]
            if balances and sum(balances) > 0:
                deciles = np.array_split(balances, 10)
                decile_sums = [sum(d) for d in deciles]
                total_w = max(1.0, float(sum(balances)))
                decile_pcts = [d_sum / total_w * 100 for d_sum in decile_sums]
                
                xs = [f"D{i+1}" for i in range(10)]
                colors_dec = [plt.cm.magma(0.2 + 0.7 * (p / max(max(decile_pcts or [1]), 0.001))) for p in decile_pcts]
                bars4 = ax4.bar(xs, decile_pcts, color=colors_dec, edgecolor=THEME_BG, width=0.7)
                for b, p in zip(bars4, decile_pcts):
                    if p > 1:
                        ax4.text(b.get_x() + b.get_width()/2, b.get_height() + 1, f"{p:.1f}%", ha='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax4.set_title("Распределение богатства по децилям (D1 = нищуки, D10 = олигархи)", fontsize=11, fontweight='bold', color=COLOR_AMBER)
                ax4.set_ylabel("% всего капитала", fontsize=8)
                top10_share = decile_pcts[-1] if decile_pcts else 0
                ax4.text(0.02, 0.85, f"Топ 10% богачей держат {top10_share:.1f}% всех шекелей борды", transform=ax4.transAxes, fontsize=9, color=COLOR_PINK, fontweight='bold')
            else:
                ax4.text(0.5, 0.5, "Данных о распределении капитала нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=10)
                ax4.set_xticks([]); ax4.set_yticks([])
                ax4.set_title("Распределение богатства по децилям", fontsize=11, fontweight='bold', color=COLOR_AMBER)

            # 5. Items Status
            c.execute("""
                SELECT 
                    COUNT(CASE WHEN active_items LIKE '%"tinfoil_hat"%' THEN 1 END) as foil,
                    COUNT(CASE WHEN active_items LIKE '%"pepperspray_gun": true%' THEN 1 END) as spray,
                    COUNT(CASE WHEN active_items LIKE '%"shit_gun": true%' THEN 1 END) as shit,
                    COUNT(CASE WHEN active_items LIKE '%"knife_gun": true%' THEN 1 END) as knife
                FROM Users
            """)
            item_row = c.fetchone()
            labels = ["Шапочки", "Перцовки", "Говнометы", "Заточки"]
            counts = [
                (item_row['foil'] or 0) if item_row else 0,
                (item_row['spray'] or 0) if item_row else 0,
                (item_row['shit'] or 0) if item_row else 0,
                (item_row['knife'] or 0) if item_row else 0
            ]
            ax5.barh(labels, counts, color=[COLOR_CYAN, COLOR_AMBER, COLOR_GREEN, COLOR_PINK], edgecolor=THEME_BG, height=0.6)
            for i, v in enumerate(counts):
                ax5.text(v + max(counts or [1])*0.03, i, str(v), va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
            ax5.set_xlim(0, max(max(counts or [1]) * 1.3, 1))
            ax5.set_title("Активный арсенал на руках", fontsize=11, fontweight='bold', color=COLOR_CYAN)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME_BG, edgecolor='none', bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        return buf


# -----------------------------------------------------------------------------
# 3. HD Poster 2: PvP & Bioweapon Warfare (1200x675)
# -----------------------------------------------------------------------------
def generate_pvp_bioweapons_poster() -> io.BytesIO:
    """Generates a 1200x675 dark-neon poster for PvP, Debuffs and Bioweapons."""
    with matplotlib_guard():
        apply_theme_v2()
        fig = plt.figure(figsize=(12, 6.75), dpi=100)
        fig.patch.set_facecolor(THEME_BG)

        fig.text(0.05, 0.94, "ТГАЧ ВОЙНЫ & БИООРУЖИЕ • PVP РАДАР", fontsize=18, fontweight='bold', color=COLOR_GREEN)
        fig.text(0.05, 0.905, "Статистика метания говна, блевоты, флагов UA/RU, прочности фольги и шизо-таблеток", fontsize=10, color=COLOR_TEXT_MUTED)

        gs = fig.add_gridspec(2, 3, left=0.05, right=0.95, top=0.86, bottom=0.08, hspace=0.35, wspace=0.25)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[0, 2])
        ax4 = fig.add_subplot(gs[1, 0:2])
        ax5 = fig.add_subplot(gs[1, 2])

        with contextlib.closing(connect_ro_db()) as conn:
            c = conn.cursor()

            # 1. Debuff Types
            c.execute("""
                SELECT 
                    SUM(CASE WHEN description LIKE '%говно%' OR description LIKE '%shit%' THEN 1 ELSE 0 END) as shit,
                    SUM(CASE WHEN description LIKE '%слабительн%' OR description LIKE '%curse%' THEN 1 ELSE 0 END) as curse,
                    SUM(CASE WHEN description LIKE '%шизо%' OR description LIKE '%schizo%' THEN 1 ELSE 0 END) as schizo,
                    SUM(CASE WHEN description LIKE '%пативэн%' OR description LIKE '%partyvan%' THEN 1 ELSE 0 END) as van,
                    SUM(CASE WHEN description LIKE '%перцов%' THEN 1 ELSE 0 END) as pepper
                FROM UserTransactions
                WHERE category IN ('shop', 'combat') OR description LIKE '%говно%' OR description LIKE '%слабительн%' OR description LIKE '%шизо%' OR description LIKE '%пативэн%'
            """)
            row1 = c.fetchone()
            d_labels = ["Говно/Блевота", "Слабительное", "Шизо-таблетки", "Пативэн/КПЗ", "Перцовка"]
            d_counts = [
                (row1['shit'] or 0) if row1 else 0,
                (row1['curse'] or 0) if row1 else 0,
                (row1['schizo'] or 0) if row1 else 0,
                (row1['van'] or 0) if row1 else 0,
                (row1['pepper'] or 0) if row1 else 0
            ]
            
            x_pos = range(len(d_labels))
            ax1.bar(x_pos, d_counts, color=[COLOR_GREEN, COLOR_AMBER, COLOR_PURPLE, COLOR_BLUE, COLOR_PINK], edgecolor=THEME_BG, width=0.6)
            ax1.set_xticks(list(x_pos))
            ax1.set_xticklabels(d_labels, rotation=25, ha='right', fontsize=8)
            ax1.set_title("Использованное оружие", fontsize=11, fontweight='bold', color=COLOR_GREEN)

            # 2. Tinfoil Durability
            now_ts = int(time.time())
            c.execute("""
                SELECT user_id, active_items FROM Users 
                WHERE active_items LIKE '%"tinfoil_hat"%'
            """)
            foil_users = c.fetchall()
            durations = []
            for u in foil_users:
                try:
                    items = json.loads(u['active_items'])
                    exp = items.get('tinfoil_hat', 0)
                    if exp > now_ts:
                        durations.append((exp - now_ts) / 3600.0)
                except Exception:
                    pass
            
            if durations:
                sns.boxplot(y=durations, ax=ax2, color=COLOR_CYAN)
                ax2.set_title("Запас прочности фольги (ч)", fontsize=11, fontweight='bold', color=COLOR_CYAN)
                ax2.set_ylabel("Часов до сгорания", fontsize=8)
            else:
                ax2.text(0.5, 0.5, "Активной фольги нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax2.set_xticks([]); ax2.set_yticks([])
                ax2.set_title("Запас прочности фольги (ч)", fontsize=11, fontweight='bold', color=COLOR_CYAN)

            # 3. Reflection vs Penetration (Authentic SQL)
            c.execute("""
                SELECT 
                    SUM(CASE WHEN description LIKE '%отражен%' OR description LIKE '%фольг%' THEN 1 ELSE 0 END) as refl,
                    SUM(CASE WHEN description LIKE '%попал%' OR description LIKE '%урон%' OR description LIKE '%облил%' OR description LIKE '%пырнул%' THEN 1 ELSE 0 END) as hits
                FROM UserTransactions
                WHERE category IN ('shop', 'combat')
            """)
            tx_shield_row = c.fetchone()
            refl = (tx_shield_row['refl'] or 0) if tx_shield_row else 0
            hits = (tx_shield_row['hits'] or 0) if tx_shield_row else 0

            c.execute("""
                SELECT 
                    COUNT(CASE WHEN active_items LIKE '%"tinfoil_hat"%' THEN 1 END) as shielded,
                    COUNT(CASE WHEN active_items NOT LIKE '%"tinfoil_hat"%' OR active_items IS NULL THEN 1 END) as exposed
                FROM Users
            """)
            u_shield_row = c.fetchone()
            shielded = (u_shield_row['shielded'] or 0) if u_shield_row else 0
            exposed = (u_shield_row['exposed'] or 0) if u_shield_row else 0

            if refl > 0 or hits > 0:
                slices = [refl, hits]
                labels = ["Отражено фольгой", "Прямые попадания"]
            elif shielded > 0 or exposed > 0:
                slices = [shielded, exposed]
                labels = ["Под защитой фольги", "Без защиты (уязвимы)"]
            else:
                slices = []

            if slices and sum(slices) > 0:
                ax3.pie(slices, labels=labels, colors=[COLOR_CYAN, COLOR_PINK],
                        autopct='%1.0f%%', startangle=120, wedgeprops=dict(width=0.45, edgecolor=THEME_BG, linewidth=2),
                        textprops=dict(color=COLOR_TEXT_MAIN, fontsize=8, fontweight='bold'))
                ax3.set_title("Точность & Рикошеты", fontsize=11, fontweight='bold', color=COLOR_AMBER)
            else:
                ax3.text(0.5, 0.5, "Данных по защите нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax3.set_xticks([]); ax3.set_yticks([])
                ax3.set_title("Точность & Рикошеты", fontsize=11, fontweight='bold', color=COLOR_AMBER)

            # 4. Timeline (Padded to 7 days for smooth visualization)
            c.execute("""
                SELECT date(timestamp, 'unixepoch', 'localtime') as d, COUNT(*) as cnt
                FROM UserTransactions
                WHERE category IN ('shop', 'combat')
                GROUP BY d ORDER BY d
            """)
            t_rows = [dict(r) for r in c.fetchall()]
            
            # Pad 7 days
            day_map = {r['d']: r['cnt'] for r in t_rows}
            date_list = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
            counts_padded = [day_map.get(dt, 0) for dt in date_list]
            
            xs = range(len(date_list))
            ax4.fill_between(xs, counts_padded, color=COLOR_PINK, alpha=0.25)
            ax4.plot(xs, counts_padded, color=COLOR_PINK, marker='o', linewidth=2)
            ax4.set_xticks(list(xs))
            ax4.set_xticklabels([d[5:] for d in date_list], rotation=0, ha='center', fontsize=8)
            ax4.set_title("Интенсивность боевых действий по дням (7д)", fontsize=11, fontweight='bold', color=COLOR_PINK)
            ax4.set_ylabel("Применений оружия", fontsize=8)

            # 5. Mutes
            now_ts = time.time()
            c.execute("""
                SELECT mute_type, COUNT(*) as cnt 
                FROM Mutes 
                WHERE expires_at > ?
                GROUP BY mute_type ORDER BY cnt DESC LIMIT 4
            """, (now_ts,))
            m_rows = c.fetchall()
            if m_rows:
                m_lbls = [r['mute_type'][:10] for r in m_rows]
                m_cnts = [r['cnt'] for r in m_rows]
                ax5.barh(m_lbls, m_cnts, color=COLOR_PURPLE, edgecolor=THEME_BG, height=0.6)
                for i, v in enumerate(m_cnts):
                    ax5.text(v + max(m_cnts)*0.03, i, str(v), va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax5.set_xlim(0, max(max(m_cnts) * 1.3, 1))
            else:
                ax5.text(0.5, 0.5, "Активных мутов нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax5.set_xticks([]); ax5.set_yticks([])
            ax5.set_title("Активные муты и баны", fontsize=11, fontweight='bold', color=COLOR_PURPLE)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME_BG, edgecolor='none', bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        return buf


# -----------------------------------------------------------------------------
# 4. HD Poster 3: Viral Memetics & Bayano-Meter (1200x675)
# -----------------------------------------------------------------------------
def generate_bayan_memetics_poster() -> io.BytesIO:
    """Generates a 1200x675 dark-neon poster for Viral Memetics & Bayano-meter."""
    with matplotlib_guard():
        apply_theme_v2()
        fig = plt.figure(figsize=(12, 6.75), dpi=100)
        fig.patch.set_facecolor(THEME_BG)

        fig.text(0.05, 0.94, "ТГАЧ БАЯНОМЕТР & МЕМЕТИКА • КАРТА ВИРУСОВ", fontsize=18, fontweight='bold', color=COLOR_CYAN)
        fig.text(0.05, 0.905, "Топ форсимых картинок (pHash кластеры), семантика AI-тегов, сленговый дрейф и копипасты", fontsize=10, color=COLOR_TEXT_MUTED)

        gs = fig.add_gridspec(2, 3, left=0.05, right=0.95, top=0.86, bottom=0.08, hspace=0.35, wspace=0.25)
        ax1 = fig.add_subplot(gs[0, 0:2])
        ax2 = fig.add_subplot(gs[0, 2])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])
        ax5 = fig.add_subplot(gs[1, 2])

        with contextlib.closing(connect_ro_db()) as conn:
            c = conn.cursor()

            # 1. Top Viral Reposts
            c.execute("""
                SELECT file_unique_id, times, first_seen
                FROM MediaReposts
                ORDER BY times DESC LIMIT 7
            """)
            bayans = c.fetchall()
            if bayans:
                b_ids = [f"Мем #{r['file_unique_id'][:8]}" for r in bayans]
                b_times = [r['times'] for r in bayans]
                b_ids.reverse(); b_times.reverse()
                bars1 = ax1.barh(b_ids, b_times, color=COLOR_CYAN, edgecolor=THEME_BG, height=0.6)
                for b, v in zip(bars1, b_times):
                    ax1.text(b.get_width() + max(b_times)*0.02, b.get_y() + b.get_height()/2, f"x{v} форсов", va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax1.set_xlim(0, max(max(b_times or [1]) * 1.25, 1))
            else:
                ax1.text(0.5, 0.5, "Данных по репостам пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=10)
                ax1.set_xticks([]); ax1.set_yticks([])
            ax1.set_title("Топ-7 Главных Баянов Борды (Количество репостов)", fontsize=11, fontweight='bold', color=COLOR_CYAN)

            # 2. Top Vision AI Tags
            c.execute("""
                SELECT tags FROM FileRegistry 
                WHERE tags IS NOT NULL AND tags != '' AND tags != 'parse_error'
                ORDER BY created_at DESC LIMIT 300
            """)
            tag_rows = c.fetchall()
            tag_counter = Counter()
            for r in tag_rows:
                raw = r['tags']
                for t in str(raw).split(','):
                    t_clean = t.strip().lower()
                    if t_clean and len(t_clean) > 2 and t_clean not in ('media', 'photo', 'image'):
                        tag_counter[t_clean] += 1
            
            top_tags = tag_counter.most_common(5)
            if top_tags:
                t_lbls = [t[0][:10] for t in top_tags]
                t_cnts = [t[1] for t in top_tags]
                ax2.pie(t_cnts, labels=t_lbls, colors=[COLOR_PINK, COLOR_PURPLE, COLOR_BLUE, COLOR_GREEN, COLOR_AMBER],
                        autopct='%1.0f%%', startangle=140, wedgeprops=dict(width=0.45, edgecolor=THEME_BG, linewidth=2),
                        textprops=dict(color=COLOR_TEXT_MAIN, fontsize=8, fontweight='bold'))
            else:
                ax2.text(0.5, 0.5, "AI-тегов пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax2.set_xticks([]); ax2.set_yticks([])
            ax2.set_title("Доминирующие AI-теги картинок", fontsize=11, fontweight='bold', color=COLOR_PURPLE)

            # 3. Slang Life Cycle (Single-pass efficient query)
            c.execute("""
                SELECT 
                    SUM(CASE WHEN content LIKE '%скуф%' THEN 1 ELSE 0 END) as skuf,
                    SUM(CASE WHEN content LIKE '%гойда%' THEN 1 ELSE 0 END) as goyda,
                    SUM(CASE WHEN content LIKE '%альтушка%' THEN 1 ELSE 0 END) as alt,
                    SUM(CASE WHEN content LIKE '%база%' THEN 1 ELSE 0 END) as baza,
                    SUM(CASE WHEN content LIKE '%сояк%' THEN 1 ELSE 0 END) as soyak,
                    SUM(CASE WHEN content LIKE '%сигма%' THEN 1 ELSE 0 END) as sigma
                FROM Posts
                WHERE timestamp > (strftime('%s', 'now') - 30 * 86400)
            """)
            slang_row = c.fetchone()
            slang_words = ["скуф", "гойда", "альтушка", "база", "сояк", "сигма"]
            if slang_row:
                slang_counts = [
                    (slang_row['skuf'] or 0),
                    (slang_row['goyda'] or 0),
                    (slang_row['alt'] or 0),
                    (slang_row['baza'] or 0),
                    (slang_row['soyak'] or 0),
                    (slang_row['sigma'] or 0)
                ]
            else:
                slang_counts = [0, 0, 0, 0, 0, 0]
            
            x_pos = range(len(slang_words))
            ax3.bar(x_pos, slang_counts, color=[COLOR_AMBER, COLOR_PINK, COLOR_PURPLE, COLOR_GREEN, COLOR_CYAN, COLOR_BLUE], edgecolor=THEME_BG)
            ax3.set_xticks(list(x_pos))
            ax3.set_xticklabels(slang_words, rotation=25, ha='right', fontsize=8)
            ax3.set_title("Мем-Словарь & Сленг (30д)", fontsize=11, fontweight='bold', color=COLOR_AMBER)

            # 4. Copypasta vs Original (Authentic calculation from Posts)
            c.execute("""
                SELECT 
                    COUNT(CASE WHEN LENGTH(content) < 15 THEN 1 END) as short_cnt,
                    COUNT(CASE WHEN LENGTH(content) >= 15 THEN 1 END) as long_cnt,
                    COUNT(*) as total_cnt
                FROM Posts 
                WHERE timestamp > (strftime('%s', 'now') - 30 * 86400) AND content IS NOT NULL
            """)
            pasta_row = c.fetchone()
            c.execute("""
                SELECT COUNT(*) as dup_cnt FROM (
                    SELECT content FROM Posts
                    WHERE timestamp > (strftime('%s', 'now') - 30 * 86400) AND LENGTH(content) >= 20
                    GROUP BY content HAVING COUNT(*) > 1
                )
            """)
            dup_row = c.fetchone()
            total_p = (pasta_row['total_cnt'] or 0) if pasta_row else 0
            short_p = (pasta_row['short_cnt'] or 0) if pasta_row else 0
            dup_p = (dup_row['dup_cnt'] or 0) if dup_row else 0
            orig_p = max(0, total_p - short_p - dup_p)

            if total_p > 0:
                raw_slices = [orig_p, dup_p, short_p]
                raw_labels = ["Оригинальные", "Пасты/Баяны", "Односложные"]
                raw_colors = [COLOR_GREEN, COLOR_AMBER, COLOR_PINK]
                slices_clean = []
                labels_clean = []
                colors_clean = []
                for s, l, col in zip(raw_slices, raw_labels, raw_colors):
                    if s > 0:
                        slices_clean.append(s)
                        labels_clean.append(l)
                        colors_clean.append(col)
                if not slices_clean:
                    slices_clean = [1]
                    labels_clean = ["Оригинальные"]
                    colors_clean = [COLOR_GREEN]

                ax4.pie(slices_clean, labels=labels_clean, colors=colors_clean,
                        autopct='%1.0f%%', startangle=140, wedgeprops=dict(width=0.45, edgecolor=THEME_BG, linewidth=2),
                        textprops=dict(color=COLOR_TEXT_MAIN, fontsize=8, fontweight='bold'))
            else:
                ax4.text(0.5, 0.5, "Текстов пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax4.set_xticks([]); ax4.set_yticks([])
            ax4.set_title("Индекс Пастообразности", fontsize=11, fontweight='bold', color=COLOR_GREEN)

            # 5. Media Format Distribution
            c.execute("""
                SELECT 
                    SUM(CASE WHEN content LIKE '%"type": "photo"%' THEN 1 ELSE 0 END) as photo,
                    SUM(CASE WHEN content LIKE '%"type": "video"%' THEN 1 ELSE 0 END) as video,
                    SUM(CASE WHEN content LIKE '%"type": "animation"%' THEN 1 ELSE 0 END) as gif,
                    SUM(CASE WHEN content LIKE '%"type": "sticker"%' THEN 1 ELSE 0 END) as sticker
                FROM Posts WHERE timestamp > (strftime('%s', 'now') - 30 * 86400)
            """)
            m_row = c.fetchone()
            m_lbls = ["Фото", "Видео", "GIF", "Стикеры"]
            if m_row:
                m_vals = [m_row['photo'] or 0, m_row['video'] or 0, m_row['gif'] or 0, m_row['sticker'] or 0]
            else:
                m_vals = [0, 0, 0, 0]
            ax5.barh(m_lbls, m_vals, color=[COLOR_BLUE, COLOR_PINK, COLOR_AMBER, COLOR_PURPLE], edgecolor=THEME_BG, height=0.6)
            for i, v in enumerate(m_vals):
                ax5.text(v + max(m_vals or [1])*0.03, i, str(v), va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
            ax5.set_xlim(0, max(max(m_vals or [1]) * 1.3, 1))
            ax5.set_title("Форматы медиа (30д)", fontsize=11, fontweight='bold', color=COLOR_BLUE)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME_BG, edgecolor='none', bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        return buf


# -----------------------------------------------------------------------------
# 5. HD Poster 4: Sociology, Drama & Beef Matrix (1200x675)
# -----------------------------------------------------------------------------
def generate_drama_beef_poster() -> io.BytesIO:
    """Generates a 1200x675 dark-neon poster for Sociology, Drama, and Nemesis Pairs."""
    with matplotlib_guard():
        apply_theme_v2()
        fig = plt.figure(figsize=(12, 6.75), dpi=100)
        fig.patch.set_facecolor(THEME_BG)

        fig.text(0.05, 0.94, "ТГАЧ СОЦИОЛОГИЯ & БИФЫ • КАРТА ДРАМЫ", fontsize=18, fontweight='bold', color=COLOR_PINK)
        fig.text(0.05, 0.905, "Матрица взаимной вражды (Beef Index), токсичность досок, вампиризм внимания и ночная шизофазия", fontsize=10, color=COLOR_TEXT_MUTED)

        gs = fig.add_gridspec(2, 3, left=0.05, right=0.95, top=0.86, bottom=0.08, hspace=0.35, wspace=0.25)
        ax1 = fig.add_subplot(gs[0, 0:2]) # Nemesis Pairs
        ax2 = fig.add_subplot(gs[0, 2])   # Toxicity Radar/Bar per board
        ax3 = fig.add_subplot(gs[1, 0])   # Attention Vampires vs Donors
        ax4 = fig.add_subplot(gs[1, 1:3]) # Night Schizo Wave (00:00 - 06:00)

        with contextlib.closing(connect_ro_db()) as conn:
            c = conn.cursor()

            # 1. Nemesis Pairs (30-day time window for fast indexed join)
            c.execute("""
                SELECT 
                    repl.author_id as u1,
                    orig.author_id as u2,
                    COUNT(*) as clashes
                FROM Posts repl
                JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
                WHERE repl.timestamp > (strftime('%s', 'now') - 30 * 86400)
                  AND orig.timestamp > (strftime('%s', 'now') - 30 * 86400)
                  AND repl.author_id IS NOT NULL AND orig.author_id IS NOT NULL 
                  AND repl.author_id != orig.author_id
                  AND (repl.content LIKE '%хуй%' OR repl.content LIKE '%бля%' OR repl.content LIKE '%пизд%' OR repl.content LIKE '%сояк%' OR repl.content LIKE '%шиз%')
                GROUP BY u1, u2
                ORDER BY clashes DESC LIMIT 6
            """)
            beef_rows = c.fetchall()
            if beef_rows:
                pair_labels = [f"{generate_anon_name(r['u1']).split('(')[0][:10]} vs {generate_anon_name(r['u2']).split('(')[0][:10]}" for r in beef_rows]
                clash_cnts = [(r['clashes'] or 0) for r in beef_rows]
                pair_labels.reverse(); clash_cnts.reverse()
                bars1 = ax1.barh(pair_labels, clash_cnts, color=COLOR_PINK, edgecolor=THEME_BG, height=0.6)
                for b, v in zip(bars1, clash_cnts):
                    ax1.text(b.get_width() + max(clash_cnts)*0.02, b.get_y() + b.get_height()/2, f"{v} стычек", va='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax1.set_xlim(0, max(max(clash_cnts or [1]) * 1.3, 1))
                ax1.set_title("Топ-6 Заклятых Врагов Борды (Beef Intensity Index)", fontsize=11, fontweight='bold', color=COLOR_PINK)
            else:
                ax1.text(0.5, 0.5, "Данных по открытым бифам пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=10)
                ax1.set_xticks([]); ax1.set_yticks([])
                ax1.set_title("Топ-6 Заклятых Врагов Борды", fontsize=11, fontweight='bold', color=COLOR_PINK)

            # 2. Board Toxicity % (Swear rate)
            c.execute("""
                SELECT board_id, 
                       COUNT(*) as total,
                       SUM(CASE WHEN content LIKE '%хуй%' OR content LIKE '%бля%' OR content LIKE '%пизд%' OR content LIKE '%еба%' THEN 1 ELSE 0 END) as toxic
                FROM Posts
                WHERE timestamp > (strftime('%s', 'now') - 30 * 86400)
                GROUP BY board_id HAVING total >= 5
                ORDER BY (CAST(toxic as float)/total) DESC LIMIT 5
            """)
            tox_rows = c.fetchall()
            if tox_rows:
                b_names = [f"/{r['board_id']}/" for r in tox_rows]
                tox_pcts = [round(((r['toxic'] or 0) / max(1, r['total'])) * 100, 1) for r in tox_rows]
                ax2.bar(b_names, tox_pcts, color=[COLOR_PINK, COLOR_PURPLE, COLOR_AMBER, COLOR_CYAN, COLOR_BLUE][:len(tox_rows)], edgecolor=THEME_BG, width=0.6)
                for i, p in enumerate(tox_pcts):
                    ax2.text(i, p + 1, f"{p}%", ha='center', fontsize=8, color=COLOR_TEXT_MAIN, fontweight='bold')
                ax2.set_title("Токсичность досок (% мата)", fontsize=11, fontweight='bold', color=COLOR_PINK)
                ax2.set_ylabel("% токсичных постов", fontsize=8)
            else:
                ax2.text(0.5, 0.5, "Данных недостаточно", ha='center', va='center', color=COLOR_TEXT_MUTED)
                ax2.set_xticks([]); ax2.set_yticks([])
                ax2.set_title("Токсичность досок (% мата)", fontsize=11, fontweight='bold', color=COLOR_PINK)

            # 3. Attention Vampires vs Donors
            c.execute("""
                SELECT author_id, COUNT(*) as posts_cnt 
                FROM Posts WHERE author_id IS NOT NULL AND timestamp > (strftime('%s', 'now') - 30 * 86400)
                GROUP BY author_id ORDER BY posts_cnt DESC LIMIT 8
            """)
            top_posters = c.fetchall()
            if top_posters:
                vamp_names = [generate_anon_name(r['author_id']).split('(')[0][:10] for r in top_posters]
                vamp_posts = [(r['posts_cnt'] or 0) for r in top_posters]
                vamp_names.reverse(); vamp_posts.reverse()
                ax3.barh(vamp_names, vamp_posts, color=COLOR_PURPLE, edgecolor=THEME_BG, height=0.6)
                ax3.set_xlim(0, max(max(vamp_posts or [1]) * 1.25, 1))
            else:
                ax3.text(0.5, 0.5, "Постов пока нет", ha='center', va='center', color=COLOR_TEXT_MUTED, fontsize=9)
                ax3.set_xticks([]); ax3.set_yticks([])
            ax3.set_title("Лидеры поглощения внимания", fontsize=11, fontweight='bold', color=COLOR_PURPLE)
            ax3.set_xlabel("Постов за 30 дней", fontsize=8)

            # 4. Night Schizo Wave (00:00 - 06:00 vs Day)
            c.execute("""
                SELECT 
                    cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                    COUNT(*) as cnt
                FROM Posts
                WHERE timestamp > (strftime('%s', 'now') - 30 * 86400)
                GROUP BY h ORDER BY h
            """)
            h_rows = {r['h']: r['cnt'] for r in c.fetchall()}
            hours_24 = list(range(24))
            counts_24 = [h_rows.get(h, 0) for h in hours_24]
            
            colors_24 = [COLOR_PURPLE if 1 <= h <= 5 else COLOR_CYAN for h in hours_24]
            ax4.bar(hours_24, counts_24, color=colors_24, edgecolor=THEME_BG, width=0.8)
            ax4.set_xticks(hours_24[::2])
            ax4.set_xticklabels([f"{h:02d}:00" for h in hours_24[::2]], fontsize=8)
            ax4.set_title("Циркадный профиль постинга (Фиолетовым: Зона ночного психоза 01:00-05:00)", fontsize=11, fontweight='bold', color=COLOR_PURPLE)
            ax4.set_ylabel("Постов в час (30д)", fontsize=8)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=THEME_BG, edgecolor='none', bbox_inches='tight')
        plt.close('all')
        buf.seek(0)
        return buf


# -----------------------------------------------------------------------------
# 5. Requirement R5: Deep Database Sentiment & Moderation Forensics
# -----------------------------------------------------------------------------

def run_db_sentiment_moderation_forensics(
    db_path: str = "file:dvach_bot.db?mode=ro",
    conn: Optional[sqlite3.Connection] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Executes forensic inspections across Posts, Reports, Mutes, and UserTransactions.
    Extracts structured sentiment metrics on AI interventions, PvP fairness, economy balance,
    and moderation efficacy. Safe read-only execution.
    """
    close_conn = False
    if conn is None:
        conn = connect_ro_db(db_path)
        close_conn = True

    try:
        c = conn.cursor()
        now_ts = time.time()
        start_ts = now_ts - (days * 86400)

        # 1. AI Interventions & Reply Sentiment
        c.execute("SELECT COUNT(*) FROM Posts WHERE author_id = 0 AND timestamp > ?", (start_ts,))
        ai_posts_count = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*)
            FROM Posts repl
            JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
            WHERE orig.author_id = 0 AND repl.timestamp > ?
        """, (start_ts,))
        ai_replies_count = c.fetchone()[0] or 0

        c.execute("""
            SELECT COALESCE(repl.text_content, repl.content)
            FROM Posts repl
            JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
            WHERE orig.author_id = 0 AND repl.timestamp > ?
        """, (start_ts,))
        ai_reply_texts = []
        for r in c.fetchall():
            raw = r[0] or ""
            if raw.startswith("{") and raw.endswith("}"):
                try:
                    raw = json.loads(raw).get("text", raw)
                except Exception:
                    pass
            ai_reply_texts.append(raw)

        # Token sentiment scoring on AI replies
        PRAISE_TOKENS = ["база", "сигма", "хорош", "гигачад", "красава", "увожение", "мощно", "годно", "гений"]
        HOSTILITY_TOKENS = ["хуй", "бля", "пизд", "еба", "сояк", "шиз", "заткнись", "говно", "высер", "душный", "кринж"]
        FEAR_TOKENS = ["страшно", "жесть", "пощади", "ужас", "ппц", "rip", "молчу"]

        ai_sentiment_counts = {"praise": 0, "hostility": 0, "fear": 0, "neutral": 0}
        for txt in ai_reply_texts:
            lower_txt = txt.lower()
            p_score = sum(1 for t in PRAISE_TOKENS if t in lower_txt)
            h_score = sum(1 for t in HOSTILITY_TOKENS if t in lower_txt)
            f_score = sum(1 for t in FEAR_TOKENS if t in lower_txt)

            if p_score > h_score and p_score > f_score:
                ai_sentiment_counts["praise"] += 1
            elif h_score > p_score and h_score > f_score:
                ai_sentiment_counts["hostility"] += 1
            elif f_score > p_score and f_score > h_score:
                ai_sentiment_counts["fear"] += 1
            else:
                ai_sentiment_counts["neutral"] += 1

        # 2. General Board Sentiment & Hostility Breakdown
        c.execute("""
            SELECT 
                COUNT(*) as total_posts,
                SUM(CASE WHEN content LIKE '%база%' OR content LIKE '%сигма%' OR content LIKE '%годно%' OR content LIKE '%топ%' THEN 1 ELSE 0 END) as positive_posts,
                SUM(CASE WHEN content LIKE '%хуй%' OR content LIKE '%бля%' OR content LIKE '%пизд%' OR content LIKE '%еба%' THEN 1 ELSE 0 END) as toxic_posts,
                SUM(CASE WHEN content LIKE '%казино%' OR content LIKE '%рулетка%' OR content LIKE '%кости%' OR content LIKE '%дуэль%' OR content LIKE '%джекпот%' THEN 1 ELSE 0 END) as pvp_posts,
                SUM(CASE WHEN content LIKE '%подкрут%' OR content LIKE '%скам%' OR content LIKE '%наеб%' OR content LIKE '%слив%' THEN 1 ELSE 0 END) as scam_complaint_posts
            FROM Posts
            WHERE timestamp > ?
        """, (start_ts,))
        row_sent = c.fetchone()
        total_posts = row_sent[0] if row_sent else 0
        positive_posts = row_sent[1] if row_sent else 0
        toxic_posts = row_sent[2] if row_sent else 0
        pvp_posts = row_sent[3] if row_sent else 0
        scam_complaint_posts = row_sent[4] if row_sent else 0

        # 3. Moderation Forensics (Mutes, Bans, Reports)
        c.execute("SELECT COUNT(*) FROM Mutes")
        total_mutes_in_db = c.fetchone()[0] or 0

        c.execute("""
            SELECT mute_type, COUNT(*) as cnt
            FROM Mutes
            GROUP BY mute_type
        """)
        mutes_by_type = {r['mute_type']: r['cnt'] for r in c.fetchall()}

        c.execute("PRAGMA table_info(Mutes)")
        mutes_cols = {r[1] for r in c.fetchall()}
        top_mute_reasons = []
        if 'reason' in mutes_cols:
            c.execute("""
                SELECT reason, COUNT(*) as cnt
                FROM Mutes
                WHERE reason IS NOT NULL AND reason != ''
                GROUP BY reason
                ORDER BY cnt DESC LIMIT 5
            """)
            top_mute_reasons = [(r['reason'], r['cnt']) for r in c.fetchall()]

        c.execute("SELECT COUNT(*) FROM Reports WHERE created_at > ?", (start_ts,))
        total_reports = c.fetchone()[0] or 0

        c.execute("""
            SELECT category, COUNT(*) as cnt
            FROM Reports
            WHERE created_at > ?
            GROUP BY category
            ORDER BY cnt DESC
        """, (start_ts,))
        reports_by_category = {r['category']: r['cnt'] for r in c.fetchall()}

        c.execute("""
            SELECT status, COUNT(*) as cnt
            FROM Reports
            WHERE created_at > ?
            GROUP BY status
        """, (start_ts,))
        reports_by_status = {r['status']: r['cnt'] for r in c.fetchall()}

        # 4. Economy & PvP Transaction Forensics
        c.execute("""
            SELECT category, COUNT(*) as cnt, COALESCE(SUM(ABS(amount)), 0) as vol
            FROM UserTransactions
            WHERE timestamp > ?
            GROUP BY category
            ORDER BY vol DESC
        """, (start_ts,))
        tx_breakdown = {r['category']: {"count": r['cnt'], "volume": r['vol']} for r in c.fetchall()}

        # False report / arrest count from transactions
        c.execute("""
            SELECT COUNT(*)
            FROM UserTransactions
            WHERE description LIKE '%Арест за ложный донос%' AND timestamp > ?
        """, (start_ts,))
        false_report_arrests = c.fetchone()[0] or 0

        # Robbery vs fine forensics
        c.execute("""
            SELECT COUNT(*), COALESCE(SUM(ABS(amount)), 0)
            FROM UserTransactions
            WHERE category = 'rob' AND amount < 0 AND timestamp > ?
        """, (start_ts,))
        rob_fines_row = c.fetchone()
        rob_fines_count = rob_fines_row[0] if rob_fines_row else 0
        rob_fines_vol = rob_fines_row[1] if rob_fines_row else 0

        res_data = {
            "period_days": days,
            "total_posts": total_posts,
            "ai_forensics": {
                "posts_count": ai_posts_count,
                "replies_count": ai_replies_count,
                "sentiment_distribution": ai_sentiment_counts,
                "praise_ratio": round(ai_sentiment_counts["praise"] / max(1, ai_replies_count) * 100, 1),
                "hostility_ratio": round(ai_sentiment_counts["hostility"] / max(1, ai_replies_count) * 100, 1),
                "fear_ratio": round(ai_sentiment_counts["fear"] / max(1, ai_replies_count) * 100, 1),
            },
            "sentiment_summary": {
                "positive_ratio": round(positive_posts / max(1, total_posts) * 100, 1),
                "toxicity_ratio": round(toxic_posts / max(1, total_posts) * 100, 1),
                "pvp_discussion_ratio": round(pvp_posts / max(1, total_posts) * 100, 1),
                "scam_complaint_ratio": round(scam_complaint_posts / max(1, total_posts) * 100, 1),
            },
            "moderation_forensics": {
                "total_mutes": total_mutes_in_db,
                "mutes_by_type": mutes_by_type,
                "top_mute_reasons": top_mute_reasons,
                "total_reports": total_reports,
                "reports_by_category": reports_by_category,
                "reports_by_status": reports_by_status,
                "false_report_arrests": false_report_arrests,
            },
            "economy_forensics": {
                "transactions_by_category": tx_breakdown,
                "robbery_fines_count": rob_fines_count,
                "robbery_fines_volume": rob_fines_vol,
            }
        }
        return res_data
    finally:
        if close_conn and conn:
            conn.close()


def generate_forensics_report_text(
    days: int = 7,
    db_path: str = "file:dvach_bot.db?mode=ro",
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Generates a comprehensive diagnostic forensic report string.
    """
    f = run_db_sentiment_moderation_forensics(db_path=db_path, conn=conn, days=days)
    ai_f = f["ai_forensics"]
    sent = f["sentiment_summary"]
    mod = f["moderation_forensics"]
    eco = f["economy_forensics"]

    report = (
        f"🕵️ <b>ФОРЕНЗИК-ОТЧЕТ & СЕНТИМЕНТ-АНАЛИЗ БОРДЫ</b>\n"
        f"⏱️ <i>Период выборки: последние {days} дней</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Киберчед & ИИ-Интервенции:</b>\n"
        f"• Постов ИИ: <code>{ai_f['posts_count']}</code> | Ответов анонов: <code>{ai_f['replies_count']}</code>\n"
        f"• Одобрение (База): <code>{ai_f['praise_ratio']}%</code>\n"
        f"• Агрессия/Подгорание: <code>{ai_f['hostility_ratio']}%</code>\n"
        f"• Страх/Уважение: <code>{ai_f['fear_ratio']}%</code>\n\n"
        f"💬 <b>Общий сентимент досок:</b>\n"
        f"• Позитив & База: <code>{sent['positive_ratio']}%</code>\n"
        f"• Токсичность (% мата): <code>{sent['toxicity_ratio']}%</code>\n"
        f"• Доля обсуждения PvP/Казино: <code>{sent['pvp_discussion_ratio']}%</code>\n"
        f"• Жалобы на «подкрутку/скам»: <code>{sent['scam_complaint_ratio']}%</code>\n\n"
        f"⚖️ <b>Модерация & Безопасность:</b>\n"
        f"• Активных мутов в базе: <code>{mod['total_mutes']}</code>\n"
        f"• Поступило репортов: <code>{mod['total_reports']}</code>\n"
        f"• Арестов за ложные доносы: <code>{mod['false_report_arrests']}</code>\n\n"
        f"💰 <b>Экономика:</b>\n"
        f"• Штрафов за наглый грабеж: <code>{mod['false_report_arrests']}</code> шт (<code>{eco['robbery_fines_volume']:,} ₪</code>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    return report
