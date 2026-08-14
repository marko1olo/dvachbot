from shared_state import *
import asyncio
import time
import json
import math
from datetime import datetime, timedelta, timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import io
from PIL import Image, ImageDraw, ImageFont

from common.html_utils import escape_html

import os
import tempfile
import shutil
import random
import gc
from collections import defaultdict
from datetime import timezone
UTC = timezone.utc
import pandas as pd
from common.chart_lock import ChartLockTimeout, matplotlib_guard

import logging
logger = logging.getLogger(__name__)
from common.db_pool import get_pool, db_lock
from text_assets import DVACH_STATS_CAPTIONS, DVACH_STATS_CAPTIONS_EN, DVACH_STATS_CAPTIONS_JP
from post_helpers import update_post_content, create_post, format_header
from delivery_manager import enqueue_board_message, get_board_activity_last_hours

from dataclasses import dataclass, field
from typing import Dict, Any

GRAPH_STATS_PATH = "graph.json"
GRAPH_STATS_BACKUP_PATH = "graph.json.bak"
GRAPH_STATS_RETENTION_DAYS = 90

try:
    import seaborn as sns
    GRAPH_LIBS_AVAILABLE = True
except ImportError:
    GRAPH_LIBS_AVAILABLE = False

FONTS_CACHE = []
try:
    from PIL import ImageFont
    for ff in ["arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf", "OpenSans-Regular.ttf"]:
        try:
            FONTS_CACHE.append(ImageFont.truetype(ff, 40))
            break
        except IOError:
            import traceback; traceback.print_exc()
    if not FONTS_CACHE:
        FONTS_CACHE.append(ImageFont.load_default())
except Exception:
    import traceback; traceback.print_exc()

@dataclass
class ChartContext:
    cur: Any = None
    board_id: Any = None
    since_90: Any = None
    since_180: Any = None
    BG: Any = None
    FG: Any = None
    HEAT: Any = None
    np: Any = None
    plt: Any = None
    io: Any = None
    mpl: Any = None
    defaultdict: Any = None
    dt: Any = None
    fig: Any = None
    ax: Any = None
    matplotlib_guard_acquired: bool = False
    temp_file: str = None

def _collect_board_map_totals() -> dict:

    totals = {
        "last_texts": 0,
        "last_stickers": 0,
        "last_animations": 0,
        "last_audios": 0,
        "spam_violations": 0,
        "spam_tracker_users": 0,
        "spam_tracker_items": 0,
        "reaction_rate_users": 0,
        "reaction_rate_items": 0,
        "reaction_queue_users": 0,
        "reaction_queue_items": 0,
        "last_reaction_process_time": 0,
        "last_roll_time": 0,
        "last_info_command_time": 0,
        "single_photo_counter": 0,
        "last_photo_group_id": 0,
        "message_counter": 0,
        "last_user_msgs": 0,
        "user_settings": 0,
        "thread_locks": 0,
        "anime_daily_tracker": 0,
        "image_spam_items": 0,
    }
    for board_id in BOARDS:
        b_data = board_data.get(board_id, {})
        totals["last_texts"] += _safe_len(b_data.get("last_texts", {}))
        totals["last_stickers"] += _safe_len(b_data.get("last_stickers", {}))
        totals["last_animations"] += _safe_len(b_data.get("last_animations", {}))
        totals["last_audios"] += _safe_len(b_data.get("last_audios", {}))
        totals["spam_violations"] += _safe_len(b_data.get("spam_violations", {}))
        spam_tracker = b_data.get("spam_tracker", {})
        if isinstance(spam_tracker, dict):
            totals["spam_tracker_users"] += len(spam_tracker)
            totals["spam_tracker_items"] += sum(_safe_len(items) for items in spam_tracker.values())
        reaction_tracker = b_data.get("reaction_rate_tracker", {})
        if isinstance(reaction_tracker, dict):
            totals["reaction_rate_users"] += len(reaction_tracker)
            totals["reaction_rate_items"] += sum(_safe_len(items) for items in reaction_tracker.values())
        reaction_queue = b_data.get("reaction_queue", {})
        if isinstance(reaction_queue, dict):
            totals["reaction_queue_users"] += len(reaction_queue)
            totals["reaction_queue_items"] += sum(_safe_len(items) for items in reaction_queue.values())
        for key in (
            "last_reaction_process_time", "last_roll_time", "last_info_command_time",
            "single_photo_counter", "last_photo_group_id", "message_counter",
            "last_user_msgs", "user_settings", "thread_locks", "anime_daily_tracker",
        ):
            totals[key] += _safe_len(b_data.get(key, {}))
    for timestamps in image_spam_tracker.values():
        totals["image_spam_items"] += _safe_len(timestamps)
    return totals

def _collect_task_stats() -> dict:
    try:
        all_tasks = asyncio.all_tasks()
        return {
            "total": len(all_tasks),
            "done": sum(1 for task in all_tasks if task.done()),
        }
    except RuntimeError:
        return {"total": 0, "done": 0}

def _collect_global_maps_snapshot(pending_done: int) -> dict:
    return {
        "messages_storage": _safe_len(messages_storage),
        "post_to_messages": _safe_len(post_to_messages),
        "message_to_post": _safe_len(message_to_post),
        "shadow_fake_post_counters": _safe_len(shadow_fake_post_counters),
        "pending_edit_tasks": _safe_len(pending_edit_tasks),
        "pending_edit_done": pending_done,
        "current_media_groups": _safe_len(current_media_groups),
        "media_group_timers": _safe_len(media_group_timers),
        "posts_pending_deletion": _safe_len(posts_pending_deletion),
        "unknown_command_tracker": _safe_len(unknown_command_tracker),
        "contextual_reply_tracker": _safe_len(contextual_reply_tracker),
        "user_spam_locks": _safe_len(user_spam_locks),
        "generate_locks": _safe_len(generate_locks),
        "user_last_thread_action": _safe_len(user_last_thread_action),
        "reaction_ratelimit": _safe_len(reaction_ratelimit),
        "last_poll_creation_time": _safe_len(last_poll_creation_time),
        "last_poll_vote_time": _safe_len(last_poll_vote_time),
        "user_hourly_image_count": _safe_len(user_hourly_image_count),
        "user_hourly_image_reset": _safe_len(user_hourly_image_reset),
        "author_reaction_notify_tracker": _safe_len(author_reaction_notify_tracker),
        "network_retry_state": _safe_len(network_retry_state),
        "image_spam_tracker": _safe_len(image_spam_tracker),
        "stream_cache": _safe_len(stream_cache),
        "graph_stats": _safe_len(graph_stats),
        "roulette_events": _safe_len(ROULETTE_EVENTS),
    }

def format_board_statistics(stream: str, posts_per_hour: dict, board_data: dict, board_config: dict) -> tuple[str, str]:
    stats_lines = []
    for b_id_inner, config_inner in board_config.items():
        if b_id_inner == 'test': continue
        # Фильтр: только доски с юзернеймом (реальные)
        bot_username = config_inner.get('username')
        if not bot_username: continue

        clean_username = bot_username.replace('@', '')
        board_name_display = config_inner['name']

        # Формируем кликабельную ссылку
        display_html = f'<a href="https://t.me/{clean_username}">{board_name_display}</a>'

        hour_stat = posts_per_hour.get(b_id_inner, 0)
        total_stat = board_data[b_id_inner].get('board_post_count', 0)
        
        # Убрали <b> из шаблонов, так как теги теперь в display_html
        if stream == 'en':
            tpl = "{name} - {hour} pst/hr, total: {total}"
        elif stream == 'jp':
            tpl = "{name} - {hour} レス/時, 合計: {total}"
        else:
            tpl = "{name} - {hour} пст/час, всего: {total}"

        stats_lines.append(tpl.format(
            name=display_html,
            hour=hour_stat,
            total=total_stat
        ))
    if stream == 'en':
        header_text = "📊 Boards Statistics:\n"
        header_title = "### Statistics ###"
        captions = DVACH_STATS_CAPTIONS_EN
    elif stream == 'jp':
        header_text = "📊 板統計:\n"
        header_title = "### 統計 ###"
        captions = DVACH_STATS_CAPTIONS_JP
    else:
        header_text = "📊 Статистика досок:\n"
        header_title = "### Статистика ###"
        captions = DVACH_STATS_CAPTIONS
    full_stats_text = header_text + "\n".join(stats_lines)
    if random.random() < 0.76 and captions:
        dvach_caption = random.choice(captions)
        full_stats_text = f"{full_stats_text}\n\n<i>{dvach_caption}</i>"

    return full_stats_text, header_title

def _sync_collect_board_statistics(hour_ago, posts_meta_list):
    from collections import defaultdict
    posts_per_hour = defaultdict(int)
    for post_time, b_id in posts_meta_list:
        if post_time >= hour_ago and b_id:
            posts_per_hour[b_id] += 1
    return posts_per_hour

async def board_statistics_broadcaster():
    """
    Раз в 3 часа собирает общую статистику и рассылает на каждую доску
    локализованные версии. Названия досок кликабельны.
    """
    await asyncio.sleep(300)
    while True:
        try:
            await asyncio.sleep(14400) # 4 часа
            now = datetime.now(UTC)
            hour_ago = now - timedelta(hours=1)
            posts_meta_for_analysis = []
            async with storage_lock:
                for post_data in reversed(messages_storage.values()):
                    post_time = post_data.get('timestamp')
                    if not post_time or post_time < hour_ago:
                        break 
                    posts_meta_for_analysis.append(
                        (post_time, post_data.get('board_id'))
                    )
            loop = asyncio.get_running_loop()
            posts_per_hour = await loop.run_in_executor(
                save_executor,
                _sync_collect_board_statistics,
                hour_ago,
                posts_meta_for_analysis
            )
            for board_id in BOARDS:
                if board_id == 'test': continue
                activity = await get_board_activity_last_hours(board_id, hours=2)
                if activity < 90:
                    continue
                b_data = board_data[board_id]
                streams_to_process = ['ru']
                if board_id == 'int':
                    streams_to_process = ['en']
                elif ENABLE_MULTILANG:
                    streams_to_process = ['ru', 'en', 'jp']
                for stream in streams_to_process:
                    if board_id == 'int':
                        recipients = b_data['users']['active'] - b_data['users']['banned']
                    else:
                        if ENABLE_MULTILANG:
                            stream_users = await get_stream_active_users(board_id, stream)
                            recipients = stream_users.intersection(b_data['users']['active']) - b_data['users']['banned']
                        else:
                            if stream != 'ru': continue
                            recipients = b_data['users']['active'] - b_data['users']['banned']
                    if not recipients: continue
                    full_stats_text, header_title = format_board_statistics(stream, posts_per_hour, board_data, BOARD_CONFIG)
                    content = {"type": "text", "text": full_stats_text, "is_system_message": True, "archive_allowed": True}
                    post_num = await create_post(
                        board_id=board_id, author_id=0, content=content,
                        timestamp=now.timestamp(), is_from_site=False, stream=stream
                    )
                    if not post_num: continue
                    header = await format_header(board_id, post_num, stream=stream)
                    if board_id != 'int':
                         content['header'] = f"{header_title}\n{header}"
                    else:
                         content['header'] = header
                    await update_post_content(post_num, content)
                    async with storage_lock:
                        messages_storage[post_num] = {'author_id': 0, 'timestamp': now, 'content': content, 'board_id': board_id}
                    await enqueue_board_message(board_id, {
                        "recipients": recipients, "content": content, 
                        "post_num": post_num, "board_id": board_id
                    })
                    print(f"✅ [{board_id}] Статистика ({stream}) #{post_num} добавлена в очередь.")
        except Exception as e:
            print(f"❌ Ошибка в board_statistics_broadcaster: {e}")
            await asyncio.sleep(120)

def generate_wipe_image(text: str) -> bytes | None:
    """
    Создает изображение 512x512 с текстом, искажениями и шумом.
    Исправлена ошибка DeprecationWarning для Pillow 10+.
    """
    try:
        IMAGE_SIZE = (512, 512)
        BACKGROUND_COLOR = (20, 20, 20)
        TEXT_COLOR = (240, 240, 240)
        background = Image.new('RGBA', IMAGE_SIZE, BACKGROUND_COLOR)
        if not FONTS_CACHE:
            print("⛔ КРИТИЧЕСКАЯ ОШИБКА: Шрифты не загружены (FONTS_CACHE пуст)!")
            error_img = Image.new('RGB', IMAGE_SIZE, BACKGROUND_COLOR)
            draw = ImageDraw.Draw(error_img)
            try:
                error_font = ImageFont.load_default()
            except Exception:
                return None
            draw.multiline_text(
                (50, 200), "ERROR:\nFONTS NOT FOUND", 
                fill=(255, 50, 50), font=error_font, align="center"
            )
            buffer = io.BytesIO()
            error_img.save(buffer, format='PNG')
            return buffer.getvalue()
        font = random.choice(FONTS_CACHE)
        temp_draw = ImageDraw.Draw(background)
        MAX_TEXT_WIDTH = IMAGE_SIZE[0] - 40 
        wrapped_text = smart_wrap_text(temp_draw, text, font, MAX_TEXT_WIDTH)
        text_layer = Image.new('RGBA', IMAGE_SIZE, (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_layer)
        draw.multiline_text(
            (IMAGE_SIZE[0] / 2, IMAGE_SIZE[1] / 2),
            wrapped_text,
            font=font,
            fill=TEXT_COLOR,
            anchor="mm",
            align="center"
        )
        angle = random.uniform(-15, 15) # Уменьшил угол для читаемости
        rotated_text_layer = text_layer.rotate(angle, expand=False, resample=Image.BICUBIC)
        img_array = np.array(rotated_text_layer)
        rows, cols, channels = img_array.shape
        amplitude = random.uniform(3, 10)
        frequency = random.uniform(0.05, 0.1)
        x_indices = np.arange(cols)
        y_offsets = (amplitude * np.sin(x_indices * frequency)).astype(int)
        y_indices = np.arange(rows).reshape(-1, 1) + y_offsets.reshape(1, -1)
        y_indices = np.clip(y_indices, 0, rows - 1)
        distorted_array = np.zeros_like(img_array)
        for x in range(cols):
            shift = y_offsets[x]
            if shift > 0:
                distorted_array[shift:, x] = img_array[:-shift, x]
            elif shift < 0:
                distorted_array[:shift, x] = img_array[-shift:, x]
            else:
                distorted_array[:, x] = img_array[:, x]
        distorted_layer = Image.fromarray(distorted_array, 'RGBA')
        background.alpha_composite(distorted_layer)
        noise_array = np.random.randint(0, 50, (IMAGE_SIZE[1], IMAGE_SIZE[0]), dtype=np.uint8)
        noise_layer = Image.fromarray(noise_array, 'L').convert('RGBA')
        noise_layer.putalpha(Image.new('L', IMAGE_SIZE, 30))
        final_image = Image.alpha_composite(background, noise_layer)
        buffer = io.BytesIO()
        final_image.convert("RGB").save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()
    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА в generate_wipe_image: {e}")
        import traceback
        traceback.print_exc()
        return None

def _generate_activity_clock(ctx: ChartContext):
    # Модули берём по именам полей ChartContext (np/plt/io/mpl, без
    # подчёркивания). Подчёркивание — префикс локальных имён внутри тела,
    # а не имя поля контекста; ctx._np роняло функцию с AttributeError.
    cur, board_id, since_90, BG, FG = ctx.cur, ctx.board_id, ctx.since_90, ctx.BG, ctx.FG
    _np, _plt, _io, _mpl = ctx.np, ctx.plt, ctx.io, ctx.mpl
    cur.execute("""
        SELECT CAST(strftime('%H', timestamp,'unixepoch','localtime') AS INTEGER) as hr,
               COUNT(*) as cnt
        FROM Posts WHERE board_id=? AND timestamp > ?
        GROUP BY hr ORDER BY hr
    """, (board_id, since_90))
    hd = {r[0]: r[1] for r in cur.fetchall()}
    if not hd:
        return None
    vals = _np.array([hd.get(h, 0) for h in range(24)], dtype=float)
    vals_norm = vals / (vals.max() or 1)
    total_posts = int(vals.sum())

    fig = _plt.figure(figsize=(7, 7), facecolor=BG)
    ax  = fig.add_subplot(111, polar=True)
    ax.set_facecolor('#0a0f14')
    N     = 24
    theta = _np.linspace(0, 2*_np.pi, N, endpoint=False) - _np.pi/2
    width = 2*_np.pi / N * 0.82
    cmap  = _mpl.colormaps['RdYlGn']
    ax.bar(theta, vals_norm, width=width, bottom=0.12,
           color=[cmap(v) for v in vals_norm], alpha=0.92,
           edgecolor=BG, linewidth=0.7)
    for i in range(24):
        ax.text(theta[i], 1.26, f'{i:02d}', ha='center', va='center',
                fontsize=8, color=FG,
                fontweight='bold' if i in [0,6,12,18] else 'normal')
    peak_hr = int(_np.argmax(vals))
    ax.bar(theta[peak_hr], vals_norm[peak_hr], width=width, bottom=0.12,
           color='#80ffaa', alpha=0.95, edgecolor=BG, linewidth=0.7)
    quiet_hr = int(_np.argmin(vals))
    ax.bar(theta[quiet_hr], vals_norm[quiet_hr], width=width, bottom=0.12,
           color='#f78166', alpha=0.95, edgecolor=BG, linewidth=0.7)
    ax.set_ylim(0, 1.42); ax.set_yticks([]); ax.set_xticks([])
    ax.spines['polar'].set_visible(False); ax.grid(False)
    ax.set_title(f'/{board_id}/ — Часы активности (90д)\n'
                 f'Пик: {peak_hr:02d}:00  •  Тихо: {quiet_hr:02d}:00  •  {total_posts:,} постов',
                 fontsize=11, pad=14, color=FG, fontweight='bold', y=1.06)
    ax.text(0, 0, f'{total_posts//1000}k', ha='center', va='center',
            fontsize=14, color=FG, fontweight='bold', alpha=0.55)
    _plt.tight_layout()
    buf = _io.BytesIO()
    _plt.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor=BG)
    _plt.close()
    return buf.getvalue()

def _generate_ridge_plot(ctx: ChartContext):
    cur, board_id, since_90, BG, FG = ctx.cur, ctx.board_id, ctx.since_90, ctx.BG, ctx.FG
    _np, _plt, _io, defaultdict = ctx.np, ctx.plt, ctx.io, ctx.defaultdict
    cur.execute("""
        SELECT CAST(strftime('%w', timestamp,'unixepoch','localtime') AS INTEGER),
               CAST(strftime('%H', timestamp,'unixepoch','localtime') AS INTEGER),
               COUNT(*)
        FROM Posts WHERE board_id=? AND timestamp > ?
        GROUP BY 1, 2
    """, (board_id, since_90))
    dh = defaultdict(lambda: _np.zeros(24))
    for dow, hr, cnt in cur.fetchall():
        dh[dow][hr] = cnt
    days_ru = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб']
    day_colors = ['#f78166','#58a6ff','#79c0ff','#d2a8ff','#ffa657','#39d353','#e3b341']
    hrs = _np.arange(24)
    global_max = max((dh[d].max() for d in range(7)), default=1) or 1

    def _smooth(y, w=1):
        k = _np.ones(w*2+1)/(w*2+1)
        return _np.convolve(y, k, mode='same')

    fig, axes = _plt.subplots(7, 1, figsize=(13, 7), facecolor=BG, sharex=True)
    fig.subplots_adjust(hspace=-0.08)
    for idx, d in enumerate(range(6, -1, -1)):
        ax2 = axes[idx]
        ax2.set_facecolor(BG)
        y = _smooth(dh[d], w=1)
        y_n = y / global_max
        color = day_colors[d]
        ax2.fill_between(hrs, 0, y_n, color=color, alpha=0.42, clip_on=False)
        ax2.plot(hrs, y_n, color=color, linewidth=2, alpha=0.95, clip_on=False)
        ax2.set_xlim(-0.5, 23.5); ax2.set_ylim(0, 0.8)
        ax2.text(-0.5, 0.24, days_ru[d], ha='right', va='center',
                color=color, fontsize=9, fontweight='bold',
                transform=ax2.get_yaxis_transform())
        total_d = int(dh[d].sum())
        ax2.text(23.4, 0.40, f'{total_d//1000 if total_d>=1000 else total_d}{"k" if total_d>=1000 else ""}',
                ha='left', va='center', color=color, fontsize=7.5)
        ax2.set_yticks([]); ax2.spines[:].set_visible(False)
    axes[-1].set_xticks(hrs)
    axes[-1].set_xticklabels([f'{h:02d}' for h in hrs], fontsize=7.5)
    axes[-1].set_xlabel('Час суток', color=FG, fontsize=9)
    fig.suptitle(f'/{board_id}/ — Ритм по дням недели (90д)', fontsize=12, y=0.99,
                 color=FG, fontweight='bold')
    _plt.tight_layout(rect=[0.05, 0, 1, 0.98])
    buf2 = _io.BytesIO()
    _plt.savefig(buf2, format='png', dpi=130, bbox_inches='tight', facecolor=BG)
    _plt.close()
    return buf2.getvalue()

def _generate_weekday_heatmap(ctx: ChartContext):
    cur, board_id, since_180, BG, FG, HEAT = ctx.cur, ctx.board_id, ctx.since_180, ctx.BG, ctx.FG, ctx.HEAT
    _np, _plt, _io = ctx.np, ctx.plt, ctx.io
    cur.execute("""
        SELECT CAST(strftime('%w', timestamp,'unixepoch','localtime') AS INTEGER) as dow,
               CAST(strftime('%H', timestamp,'unixepoch','localtime') AS INTEGER) as hr,
               COUNT(*) as cnt
        FROM Posts WHERE board_id=? AND timestamp > ?
        GROUP BY dow, hr
    """, (board_id, since_180))
    grid = _np.zeros((7, 24))
    for dow, hr, cnt in cur.fetchall():
        grid[dow][hr] = cnt

    days_ru_full = ['Воскресенье','Понедельник','Вторник','Среда','Четверг','Пятница','Суббота']
    fig, ax3 = _plt.subplots(figsize=(10, 4.5), facecolor=BG)
    ax3.set_facecolor(BG)
    im = ax3.imshow(grid, cmap=HEAT, aspect='auto', interpolation='nearest')

    ax3.set_xticks(range(24))
    ax3.set_xticklabels([f'{h:02d}:00' for h in range(24)], fontsize=7, rotation=45, ha='right')
    ax3.set_yticks(range(7))
    ax3.set_yticklabels(days_ru_full, fontsize=8)
    ax3.set_title(f'/{board_id}/ — Тепловая карта час × день недели (180д)', fontsize=11, pad=10, color=FG, fontweight='bold')
    ax3.set_xlabel('Час суток', color=FG, fontsize=8.5)

    cb = fig.colorbar(im, ax=ax3, pad=0.01)
    cb.ax.yaxis.set_tick_params(color=FG, labelsize=7)
    cb.set_label('постов', color=FG, fontsize=7.5)

    _plt.tight_layout()
    buf3 = _io.BytesIO()
    _plt.savefig(buf3, format='png', dpi=130, bbox_inches='tight', facecolor=BG)
    _plt.close()
    return buf3.getvalue()

def _generate_calendar_heatmap(ctx: ChartContext):
    cur, board_id, since_180, BG, FG, HEAT = ctx.cur, ctx.board_id, ctx.since_180, ctx.BG, ctx.FG, ctx.HEAT
    _np, _plt, _io, _dt = ctx.np, ctx.plt, ctx.io, ctx.dt
    cur.execute("""
        SELECT date(timestamp,'unixepoch','localtime') as day, COUNT(*)
        FROM Posts WHERE board_id=? AND timestamp > ?
        GROUP BY day ORDER BY day
    """, (board_id, since_180))
    day_data = {r[0]: r[1] for r in cur.fetchall()}

    if not day_data:
        return None

    dates_sorted = sorted(day_data.keys())
    try:
        start = _dt.date.fromisoformat(dates_sorted[0])
        end   = _dt.date.fromisoformat(dates_sorted[-1])
    except Exception as e:
        logger.error(f"⚠️ Failed to parse dates for activity calendar: {e}", exc_info=True)
        return None
    start_mon = start - _dt.timedelta(days=start.weekday())
    end_sun   = end   + _dt.timedelta(days=6 - end.weekday())
    total_days = (end_sun - start_mon).days + 1
    weeks = total_days // 7
    cal = _np.zeros((7, weeks))
    cur_date = start_mon
    for w in range(weeks):
        for d in range(7):
            cal[d][w] = day_data.get(cur_date.isoformat(), 0)
            cur_date += _dt.timedelta(days=1)

    vmax = _np.percentile(list(day_data.values()), 95) if day_data else 1

    fig, ax4 = _plt.subplots(figsize=(max(10, weeks//2), 3), facecolor=BG)
    ax4.set_facecolor(BG)
    im = ax4.imshow(cal, cmap=HEAT, aspect='auto', interpolation='nearest', vmin=0, vmax=vmax)

    # Month labels
    month_ticks, month_lbls = [], []
    cdate = start_mon
    seen = set()
    for w in range(weeks):
        ym = cdate.strftime('%b %Y')
        if ym not in seen:
            month_ticks.append(w); month_lbls.append(cdate.strftime('%b\n%Y')); seen.add(ym)
        cdate += _dt.timedelta(days=7)
    ax4.set_xticks(month_ticks); ax4.set_xticklabels(month_lbls, fontsize=7.5)
    ax4.set_yticks(range(7))
    ax4.set_yticklabels(['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], fontsize=8)
    ax4.set_title(f'/{board_id}/ — Календарь активности (180д)', fontsize=11, pad=10,
                  color=FG, fontweight='bold')
    cb = fig.colorbar(im, ax=ax4, orientation='horizontal', pad=0.18, shrink=0.35)
    cb.set_label('постов/день', color=FG, fontsize=7.5)
    cb.ax.xaxis.set_tick_params(color=FG, labelsize=7)
    _plt.tight_layout()
    buf4 = _io.BytesIO()
    _plt.savefig(buf4, format='png', dpi=130, bbox_inches='tight', facecolor=BG)
    _plt.close()
    return buf4.getvalue()

def _generate_stats_charts(board_id: str) -> list[bytes]:
    """Generate 4 activity charts for board_id. Returns list of PNG bytes."""
    # rcParams.update ниже трогает ГЛОБАЛЬНОЕ состояние pyplot, а функция
    # вызывается через run_in_executor(None, ...). См. common/chart_lock.py.
    try:
        with matplotlib_guard():
            return _generate_stats_charts_locked(board_id)
    except ChartLockTimeout as e:
        print(f"⛔ Графики /stats не построены: {e}")
        return []

def _generate_stats_charts_locked(board_id: str) -> list[bytes]:
    import io as _io
    import sqlite3 as _sqlite3
    import numpy as _np
    import matplotlib as _mpl
    _mpl.use('Agg')
    import matplotlib.pyplot as _plt
    from matplotlib.colors import LinearSegmentedColormap
    from collections import defaultdict
    import datetime as _dt

    BG, FG, GRID = '#0d1117', '#e6edf3', '#21262d'
    _plt.rcParams.update({
        'figure.facecolor': BG, 'axes.facecolor': BG, 'axes.edgecolor': GRID,
        'axes.labelcolor': FG, 'xtick.color': FG, 'ytick.color': FG,
        'text.color': FG, 'grid.color': GRID, 'font.family': 'DejaVu Sans', 'font.size': 9,
    })

    import os
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dvach_bot.db')
    con = _sqlite3.connect(db_path)
    try: con.execute('PRAGMA journal_mode=WAL')
    except: pass
    try: con.execute('PRAGMA synchronous=NORMAL')
    except: pass
    try: con.execute('PRAGMA busy_timeout=15000')
    except: pass
    try: con.execute('PRAGMA wal_autocheckpoint=1000')
    except: pass
    try:
        cur = con.cursor()

        import time as _time_module
        since_90 = int(_time_module.time()) - 90 * 86400
        since_180 = int(_time_module.time()) - 180 * 86400
        bufs = []

        HEAT = LinearSegmentedColormap.from_list('dv', ['#0d1117','#003d20','#006d35','#39d353','#80ffaa'])

        ctx = ChartContext(
            cur=cur,
            board_id=board_id,
            since_90=since_90,
            since_180=since_180,
            BG=BG,
            FG=FG,
            HEAT=HEAT,
            np=_np,
            plt=_plt,
            io=_io,
            mpl=_mpl,
            defaultdict=defaultdict,
            dt=_dt,
        )

        activity_clock = _generate_activity_clock(ctx)
        if not activity_clock:
            return []
        bufs.append(activity_clock)

        ridge_plot = _generate_ridge_plot(ctx)
        if ridge_plot:
            bufs.append(ridge_plot)

        heatmap = _generate_weekday_heatmap(ctx)
        if heatmap:
            bufs.append(heatmap)

        calendar = _generate_calendar_heatmap(ctx)
        if calendar:
            bufs.append(calendar)

        return bufs
    finally:
        # Оба ресурса освобождаем безусловно. Раньше con.close() стоял на
        # двух путях возврата, и любое исключение в генераторе проходило
        # мимо обоих: соединение с sqlite (и его файловый дескриптор)
        # утекало на каждом сбое.
        con.close()
        # Фигуры matplotlib живут в ГЛОБАЛЬНОМ реестре pyplot, а не в
        # локальной переменной: незакрытая фигура не собирается сборщиком
        # мусора и держит память до конца процесса. Каждый генератор
        # закрывает свою, но только если дошёл до конца — сбой между
        # созданием фигуры и close() оставлял её висеть навсегда.
        # close('all') безопасен: вся функция идёт под matplotlib_guard(),
        # так что чужих фигур в этот момент в процессе быть не может.
        _plt.close('all')

async def _get_passport_stats(user_id: int) -> tuple[int, float, int] | None:
    post_count = 0
    balance = 0
    is_verified = 0
    try:
        async with db_lock:
            db = await get_pool()
            # Берем ГЛОБАЛЬНЫЙ баланс и статус (сумма по всем доскам)
            query = "SELECT SUM(balance), MAX(is_verified_b) FROM Users WHERE user_id = ?"
            async with db.execute(query, (user_id,)) as cursor:
                row = await cursor.fetchone()
                balance = row[0] if row and row[0] is not None else 0
                is_verified = row[1] if row and row[1] is not None else 0
            
            # Считаем ГЛОБАЛЬНОЕ количество постов (во всем боте)
            query_cnt = "SELECT COUNT(*) FROM Posts WHERE author_id = ?"
            async with db.execute(query_cnt, (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row: post_count = row[0]
    except Exception as e:
        print(f"Ошибка получения статистики: {e}")
        return None
    return post_count, balance, is_verified

def _sync_save_graph_stats(data_to_save: dict) -> bool:
    """
    Атомарно сохраняет статистику графика на диск.

    Пишем во временный файл в той же директории, фсинкаем и только потом
    подменяем боевой через os.replace (атомарен на Windows и POSIX).
    Так внезапный SIGINT от memory_restarter не может оставить обрезанный
    graph.json. Предыдущая удачная версия сохраняется в .bak.
    """
    tmp_path = ""
    try:
        directory = os.path.dirname(os.path.abspath(GRAPH_STATS_PATH))
        fd, tmp_path = tempfile.mkstemp(prefix=".graph_", suffix=".tmp", dir=directory)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Ротация бэкапа перед подменой: если новый файл окажется плохим,
        # load_graph_stats поднимет предыдущий.
        if os.path.exists(GRAPH_STATS_PATH):
            try:
                shutil.copyfile(GRAPH_STATS_PATH, GRAPH_STATS_BACKUP_PATH)
            except OSError as e:
                print(f"⚠️ Не удалось обновить {GRAPH_STATS_BACKUP_PATH}: {e}")

        os.replace(tmp_path, GRAPH_STATS_PATH)
        tmp_path = ""
        return True
    except Exception as e:
        print(f"⛔ Ошибка в потоке сохранения graph.json: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                import traceback; traceback.print_exc()

def _coerce_graph_stats(raw) -> dict:
    """
    Приводит загруженный JSON к ожидаемой форме {board_id: {iso_ts: int}}.

    Файл могли отредактировать руками или он мог прийти из старой версии,
    поэтому не доверяем структуре: _prepare_graph_data и graph_data_collector
    падают на любом не-dict значении.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for board_id, series in raw.items():
        if not isinstance(board_id, str) or not isinstance(series, dict):
            continue
        board_series = {}
        for ts_key, count in series.items():
            if not isinstance(ts_key, str):
                continue
            if isinstance(count, bool) or not isinstance(count, (int, float)):
                continue
            board_series[ts_key] = int(count)
        if board_series:
            cleaned[board_id] = board_series
    return cleaned

def _prune_graph_stats(data: dict, retention_days: int = GRAPH_STATS_RETENTION_DAYS) -> int:
    """Выбрасывает точки старше retention_days. Возвращает число удалённых."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0
    for board_id in list(data.keys()):
        series = data[board_id]
        for ts_key in list(series.keys()):
            try:
                point_dt = datetime.fromisoformat(ts_key)
            except ValueError:
                # Нераспознаваемый ключ — он всё равно уронит pd.to_datetime
                series.pop(ts_key, None)
                removed += 1
                continue
            if point_dt.tzinfo is None:
                point_dt = point_dt.replace(tzinfo=UTC)
            if point_dt < cutoff:
                series.pop(ts_key, None)
                removed += 1
        if not series:
            data.pop(board_id, None)
    return removed

def _report_graph_save_result(future) -> None:
    """Callback для run_in_executor: не даём ошибке записи утонуть без следа."""
    try:
        if future.result() is False:
            print("⚠️ graph.json не сохранён (см. ошибку выше), данные остались только в RAM.")
    except Exception as e:
        print(f"⛔ Поток сохранения graph.json упал: {type(e).__name__}: {e}")

def load_graph_stats():

    global graph_stats
    for path, label in ((GRAPH_STATS_PATH, "graph.json"), (GRAPH_STATS_BACKUP_PATH, "graph.json.bak")):
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            print(f"⚠️ Не удалось прочитать {label}: {type(e).__name__}: {e}")
            continue

        loaded = _coerce_graph_stats(raw)
        if not loaded and raw:
            print(f"⚠️ В {label} нет ни одной валидной серии "
                  f"(корень: {type(raw).__name__}), пропускаю файл.")
            continue

        dropped = _prune_graph_stats(loaded)
        graph_stats = loaded
        points = sum(len(series) for series in loaded.values())
        suffix = f", отброшено {dropped} устаревших точек" if dropped else ""
        print(f"✅ Статистика для графика ({label}) загружена: {len(loaded)} досок, {points} точек{suffix}.")
        return

    print("ℹ️ graph.json отсутствует или повреждён — статистика графика начнётся с нуля.")
    graph_stats = {}

async def graph_data_collector():
    """
    Фоновая задача, которая раз в час собирает статистику постов
    для каждой доски и сохраняет ее для построения графика.
    """
    await asyncio.sleep(60)
    while True:
        try:
            now = datetime.now(UTC)
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=5, microsecond=0)
            wait_seconds = (next_hour - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=1)
            posts_per_hour = defaultdict(int)
            async with storage_lock:
                for post_data in reversed(messages_storage.values()):
                    timestamp = post_data.get('timestamp')
                    if not timestamp:
                        continue
                    if timestamp < start_time:
                        break
                    if start_time <= timestamp < end_time:
                        board_id = post_data.get('board_id')
                        if board_id:
                            posts_per_hour[board_id] += 1
            timestamp_key = start_time.replace(minute=0, second=0, microsecond=0).isoformat()
            if not posts_per_hour:
                print(f"📊 Сборщик статистики для графика: за час с {start_time.strftime('%H:%M')} не было активности.")
                continue
            for board_id, count in posts_per_hour.items():
                if count > 0:
                    graph_stats.setdefault(board_id, {})[timestamp_key] = count
            dropped = _prune_graph_stats(graph_stats)
            pruned_note = f", подрезано {dropped} точек старше {GRAPH_STATS_RETENTION_DAYS}д" if dropped else ""
            print(f"📊 Статистика для графика собрана за {timestamp_key}. Активные доски: {list(posts_per_hour.keys())}{pruned_note}")

            # Сохраняем на диск в фоновом потоке.
            # graph_stats.copy() был поверхностным: поток сериализовал те же вложенные
            # dict'ы, которые здесь мутируются -> "dict changed size during iteration".
            # Снимаем полноценный снапшот и логируем провал записи, а не глотаем его.
            snapshot = {board_id: dict(series) for board_id, series in graph_stats.items()}
            save_future = asyncio.get_running_loop().run_in_executor(
                save_executor, _sync_save_graph_stats, snapshot
            )
            save_future.add_done_callback(_report_graph_save_result)
        except asyncio.CancelledError:
            print("ℹ️ Сборщик статистики для графика остановлен.")
            break
        except Exception as e:
            print(f"⛔ Ошибка в сборщике статистики для графика (graph_data_collector): {e}")
            await asyncio.sleep(300)

def _prepare_graph_data(board_id: str, days: int):
    """Подготавливает DataFrame для графика, фильтруя и ресемплируя данные."""
    board_data_for_graph = graph_stats.get(board_id)
    if not board_data_for_graph:
        return None
    df = pd.DataFrame.from_dict(board_data_for_graph, orient='index', columns=['posts'])
    df.index = pd.to_datetime(df.index, utc=True)
    start_date_utc = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=days)
    df_filtered = df[df.index >= start_date_utc].copy()
    if df_filtered.empty:
        return None
    resample_period = '1H' if days <= 1 else '3H'
    end_date_utc = df_filtered.index.max()
    if pd.isna(end_date_utc):
        return None
    date_range_utc = pd.date_range(start=start_date_utc, end=end_date_utc, freq=resample_period, tz='UTC')
    df_resampled = df_filtered.resample(resample_period).sum().reindex(date_range_utc).fillna(0)
    if df_resampled.empty or df_resampled['posts'].max() == 0:
        return None
    return df_resampled

def _setup_graph_axes(ax, days: int, df_resampled, board_id: str):
    """Настраивает оси, сетку и подписи графика."""
    board_name = BOARD_CONFIG.get(board_id, {}).get('name', board_id)
    period_str = f"{days} day(s)" if board_id == 'int' else f"{days} дн."
    ax.set_title(f"Активность доски {board_name} за {period_str}", fontsize=16, color='white', pad=20)

    max_val = df_resampled['posts'].max()
    if max_val < 5:
        nice_max = 5
    else:
        power = 10 ** math.floor(math.log10(max_val)) if max_val > 0 else 1
        nice_max = math.ceil(max_val / power) * power
        if nice_max * 0.8 > max_val:
             nice_max = math.ceil(max_val / (power/2)) * (power/2)
    ax.set_ylim(0, nice_max * 1.05)
    ax.set_yticks(np.linspace(0, nice_max, 6, dtype=int))
    ax.set_ylabel("Постов в час" if days <= 1 else "Постов за 3 часа", fontsize=12, color='white')

    MSK = timezone(timedelta(hours=3))
    if days <= 1:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=4, tz=MSK))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H', tz=MSK))
        ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1, tz=MSK))
        ax.set_xlabel("Время (МСК)", fontsize=12, color='white')
    else:
        day_interval = max(1, days // 7)
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=day_interval, tz=MSK))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b', tz=MSK))
        ax.xaxis.set_minor_locator(mdates.HourLocator(interval=3, tz=MSK))

    ax.set_facecolor('#0d1117')
    ax.grid(True, which='major', linestyle='--', linewidth=0.4, color='#30363d')
    ax.grid(True, which='minor', linestyle=':', linewidth=0.2, color='#21262d')
    for spine in ax.spines.values():
        spine.set_color('#30363d')
    ax.tick_params(axis='x', which='major', labelsize=10, length=6, width=1.5, colors='white', rotation=0, ha="center")
    ax.tick_params(axis='y', which='major', labelsize=10, colors='white')
    ax.tick_params(axis='both', which='minor', length=4, width=0.5)

def generate_statistics_graph(board_id: str, days: int) -> bytes | None:
    """
    Генерирует изображение графика статистики постов для указанной доски за заданный период.
    Возвращает изображение в виде байтов или None в случае ошибки.
    """
    if not GRAPH_LIBS_AVAILABLE:
        print("⛔ Зависимости для графиков (pandas, matplotlib) не установлены.")
        return None
    # Крутится в дефолтном пуле потоков (до 32 воркеров), а plt.style.use ниже
    # заменяет ГЛОБАЛЬНЫЕ rcParams. Без замка два параллельных /graph рисовали
    # друг другу чужую тему. См. common/chart_lock.py.
    try:
        with matplotlib_guard():
            return _generate_statistics_graph_locked(board_id, days)
    except ChartLockTimeout as e:
        print(f"⛔ График не построен: {e}")
        return None

def _generate_statistics_graph_locked(board_id: str, days: int) -> bytes | None:
    plt.close('all')
    try:
        df_resampled = _prepare_graph_data(board_id, days)
        if df_resampled is None:
            return None

        plt.style.use('dark_background')
        num_points = len(df_resampled)
        width = max(10, min(20, num_points * 0.3))
        height = 6 if width <= 12 else 7

        fig, ax = plt.subplots(figsize=(width, height), dpi=110)
        line_color = '#00ffff'
        ax.plot(df_resampled.index, df_resampled['posts'], color=line_color, linewidth=2.5, marker='o', markersize=4, markeredgecolor='white', markerfacecolor=line_color, zorder=10)
        ax.fill_between(df_resampled.index, df_resampled['posts'], color=line_color, alpha=0.1, zorder=5)

        _setup_graph_axes(ax, days, df_resampled, board_id)

        fig.patch.set_facecolor('#0d1117')
        fig.tight_layout(pad=1.5)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
        buf.seek(0)

        plt.close(fig)
        plt.close('all') # Закрываем вообще всё
        fig = None
        ax = None
        gc.collect()

        return buf.getvalue()
    except Exception as e:
        import traceback
        print(f"⛔ Ошибка при генерации графика: {e}\n{traceback.format_exc()}")
        if 'fig' in locals() and 'fig' in vars() and plt.fignum_exists(fig.number):
            plt.close(fig)
        return None

def _get_summarize_status_text(lang: str, length_choice: str, paragraph_count: int) -> str:
    if lang == 'en':
        if length_choice == 'short':
            status_text = f"⏳ Generating a quick summary ({paragraph_count} paragraph{'s' if paragraph_count > 1 else ''})..."
        elif paragraph_count >= 6:
            status_text = f"⏳ Preparing a detailed long-read for Telegraph ({paragraph_count} paragraphs)..."
        else:
            status_text = f"⏳ Generating summary, please wait ~30 seconds ({paragraph_count} paragraphs)..."
    elif lang == 'jp':
        status_text = f"⏳ サマリーを生成中 ({paragraph_count}段落)、30秒ほどお待ちください..."
    else:
        # Russian plural endings: 1 абзац, 2-4 абзаца, 5+ абзацев
        if paragraph_count % 10 == 1 and paragraph_count % 100 != 11:
            p_word = "абзац"
        elif paragraph_count % 10 in [2, 3, 4] and paragraph_count % 100 not in [12, 13, 14]:
            p_word = "абзаца"
        else:
            p_word = "абзацев"

        if length_choice == 'short':
            status_text = f"⏳ Генерирую быстрое саммари ({paragraph_count} {p_word})..."
        elif paragraph_count >= 6:
            status_text = f"⏳ Готовлю ебануто длинный лонгрид для Telegraph ({paragraph_count} {p_word})..."
        else:
            status_text = f"⏳ Генерирую среднее саммари ({paragraph_count} {p_word})..."

    return status_text
def smart_wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    Переносит текст по словам, основываясь на реальной пиксельной ширине.
    """
    wrapped_lines = []
    user_lines = text.split('\n')
    for line in user_lines:
        if not line:
            wrapped_lines.append('')
            continue
        words = line.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if draw.textlength(test_line, font=font) <= max_width:
                current_line += word + " "
            else:
                wrapped_lines.append(current_line.strip())
                current_line = word + " "
        wrapped_lines.append(current_line.strip())
    return "\n".join(wrapped_lines)

def _collect_runtime_snapshot() -> dict:

    queue_sizes = {board: message_queues[board].qsize() for board in BOARDS if board in message_queues}
    top_queues = sorted(queue_sizes.items(), key=lambda item: item[1], reverse=True)[:5]
    queue_age_summary = _summarize_live_queue_ages(queue_sizes)
    priority_counts = {board: _safe_len(weekly_active_users.get(board, set())) for board in BOARDS}
    pending_done = _get_pending_edit_done_count()

    return {
        "utc": datetime.now(UTC).isoformat(),
        "post_counter": state.get("post_counter", 0),
        "memory": _get_process_memory_snapshot(),
        "db_files": _get_db_file_snapshot(),
        "controlled_stop": _controlled_stop_snapshot(),
        "queues": _build_queues_snapshot(queue_sizes, top_queues, queue_age_summary),
        "delivery_priority": _build_delivery_priority_snapshot(priority_counts),
        "recipients": _recipient_counts_snapshot(),
        "durable_delivery": {
            "enabled": DURABLE_DELIVERY_QUEUE_ENABLED,
            **durable_delivery_stats,
        },
        "anime_media": _build_anime_media_snapshot(),
        "mode_punchup": {
            "enabled": MODE_PUNCHUP_ENABLED,
            "runtime_enabled": mode_punchup_runtime_enabled,
            "queue_shed_sec": MODE_PUNCHUP_QUEUE_SHED_SEC,
            "slow_log_us": MODE_PUNCHUP_SLOW_LOG_US,
            "stats": _summarize_mode_punchup_stats(),
        },
        "contextual_replies": {
            "enabled": CONTEXTUAL_REPLIES_ENABLED,
            "cooldown_sec": CONTEXTUAL_REPLY_COOLDOWN_SEC,
            "daily_limit": CONTEXTUAL_REPLY_DAILY_LIMIT,
            "groups_ru": _safe_len(CONTEXTUAL_REPLIES),
            "tracked_users": _safe_len(contextual_reply_tracker),
            "stats": dict(contextual_reply_stats),
        },
        "reply_coverage": {
            "updated_at": reply_coverage_updated_at,
            **reply_coverage_stats,
        },
        "delivery": _summarize_delivery_metrics(),
        "maps": _collect_global_maps_snapshot(pending_done),
        "board_maps": _collect_board_map_totals(),
        "board_totals": _collect_board_totals(),
        "asyncio_tasks": _collect_task_stats(),
        "gc_count": gc.get_count(),
        "tracemalloc": {
            "enabled": tracemalloc.is_tracing(),
            "current_mb": round(tracemalloc.get_traced_memory()[0] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
            "peak_mb": round(tracemalloc.get_traced_memory()[1] / 1024 / 1024, 2) if tracemalloc.is_tracing() else 0.0,
        },
    }
