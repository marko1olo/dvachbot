import sqlite3
import contextlib
import time
import json
from dataclasses import dataclass
import io
import random
import re
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from common.chart_lock import matplotlib_guard

# Use non-interactive backend
matplotlib.use('Agg')

SNS_THEME_RC = {
    "axes.facecolor": "#121212",
    "figure.facecolor": "#121212",
    "text.color": "#FFFFFF",
    "axes.labelcolor": "#FFFFFF",
    "xtick.color": "#FFFFFF",
    "ytick.color": "#FFFFFF",
    "grid.color": "#333333",
    "font.family": "sans-serif"
}


def connect_stats_db(uri_path='file:dvach_bot.db?mode=ro', timeout=15.0):
    conn = sqlite3.connect(uri_path, uri=True, timeout=timeout)
    try:
        try:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous=NORMAL;')
            conn.execute('PRAGMA busy_timeout=15000;')
        except Exception:
            pass
        return conn
    except Exception:
        conn.close()
        raise


def apply_dark_theme():
    """
    Ставит тему модуля на глобальные rcParams.

    Вызывать перед КАЖДЫМ прогоном, а не только при импорте: другие генераторы
    (main.generate_statistics_graph -> plt.style.use, main._generate_stats_charts
    -> rcParams.update) перетирают глобальные rcParams, и одного применения на
    старте процесса не хватало — после первого же /graph эти графики рисовались
    чужой темой до самого перезапуска.
    """
    plt.style.use('dark_background')
    sns.set_theme(style="darkgrid", rc=SNS_THEME_RC)


# Set dark theme for imageboard vibes
apply_dark_theme()

RU_STOP = {
    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты',
    'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'уже',
    'до', 'этого', 'этой', 'эти', 'эту', 'это', 'тот', 'где', 'кто', 'он', 'мы', 'быть', 'был', 'была', 'были', 'было', 'есть',
    'если', 'или', 'ком', 'всех', 'них', 'этот', 'чтобы', 'для', 'без', 'через', 'после', 'потому', 'этом', 'им', 'ей',
    'про', 'почему', 'зачем', 'очень', 'просто', 'тут', 'там', 'когда', 'будет', 'даже', 'всегда', 'тоже',
    'какой', 'какая', 'какие', 'свои', 'свой', 'своих', 'под', 'над', 'перед', 'при', 'всего', 'всем', 'всеми', 'тебе', 'вас',
    'как', 'так', 'это', 'был', 'была', 'будет', 'мне', 'меня', 'тебе', 'тебя', 'свой', 'свои', 'своих',
    'все', 'всё', 'всех', 'всем', 'очень', 'просто', 'было', 'были', 'быть', 'один', 'два', 'три', 'когда',
    'если', 'или', 'нет', 'да', 'уже', 'еще', 'ещё', 'только', 'вот', 'этот', 'эта', 'эти', 'это',
    'можно', 'надо', 'может', 'потом', 'больше', 'вообще', 'себя', 'которые', 'который', 'себе', 'такой', 'пока', 'лучше', 'того', 'сейчас', 'здесь', 'быть', 'было', 'будет', 'если', 'этого', 'очень', 'просто', 'чтобы',
    'какой', 'какие', 'какая', 'почему', 'зачем', 'хотя', 'тоже', 'даже', 'тут', 'там', 'где', 'когда', 'кто', 'что', 'как', 'потому',
    'также', 'такое', 'теперь', 'нужно', 'только', 'будто', 'каждый', 'будто', 'очень', 'просто', 'чтобы', 'после', 'через', 'около', 'возле', 'снова', 'опять', 'назад', 'перед', 'один', 'когда',
    # URLs, tech tags, bot specifics
    'http', 'https', 'www', 'com', 'ru', 'org', 'net', 'href', 'html', 'code', 'emoji', 'span', 'div', 'class', 'style', 'br', 'li', 'ul', 'ol', 'pre', 'img', 'src', 'width', 'height', 'alt', 'title', 'target', 'blank', 'rel', 'noopener', 'noreferrer', 'data',
    'tgach', 'тгач', 'chatbot', 'dvach', 'dvachbot', 'bot', 'id', 'user', 'author', 'posts', 'post', 'thread', 'board', 'text', 'type', 'message', 'telegram', 'entities', 'url'
}

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]

def generate_schizo_name(user_id: int) -> str:
    if not user_id: return "Анонимус"
    rng = random.Random(user_id)
    prefix = rng.choice(NICK_PREFIXES)
    suffix = rng.choice(NICK_SUFFIXES)
    return f"{prefix}-{suffix} (#{str(user_id)[-4:]})"

def save_chart(images: list, filename: str, bbox_inches=None):
    buf = io.BytesIO()
    if bbox_inches:
        plt.savefig(buf, format='png', bbox_inches=bbox_inches)
    else:
        plt.savefig(buf, format='png')
    buf.seek(0)
    images.append((filename, buf))
    plt.close()

def _generate_chart_1(thirty_days_ago, c, images):
    # 1. Объем высеров (Posts per day)
    c.execute('''
        SELECT date(timestamp, 'unixepoch', 'localtime') as d, COUNT(*) as cnt
        FROM Posts
        WHERE timestamp > ?
        GROUP BY d ORDER BY d
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10, 5))
        xs = list(range(len(df)))
        ax.fill_between(xs, df['cnt'], alpha=0.18, color='#ff3366')
        sns.lineplot(data=df, x='d', y='cnt', marker='o', color='#ff3366', ax=ax)
        mean_v = df['cnt'].mean()
        ax.axhline(mean_v, color='#ffaa44', linestyle='--', linewidth=1, alpha=0.7)
        ax.text(len(df)*0.01, mean_v * 1.03, f'Среднее: {mean_v:.0f}', color='#ffaa44', fontsize=8)
        plt.title('1. Объем высеров (Посты по дням)', fontsize=16, fontweight='bold', color='#ff3366')
        plt.xticks(rotation=45)
        plt.tight_layout()
        save_chart(images, '1_posts.png')

def _generate_chart_2(c, images):
    # 2. Уникальные шизы (Weekly Active Users) — улучшенное
    c.execute('''
        SELECT strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as week,
               COUNT(DISTINCT author_id) as cnt
        FROM Posts
        WHERE timestamp > ?
        GROUP BY week ORDER BY week
    ''', (time.time() - (60 * 24 * 3600),))
    data = c.fetchall()
    if data:
        import numpy as _np
        df = pd.DataFrame(data)
        weeks = df['week'].tolist()
        counts = df['cnt'].tolist()
        xs = list(range(len(weeks)))

        # Gradient bars: color by value (low=cool, high=warm)
        cmap_wau = plt.get_cmap('YlGnBu')
        max_c = max(counts) or 1
        bar_colors = [cmap_wau(0.3 + 0.65 * v / max_c) for v in counts]

        fig, ax = plt.subplots(figsize=(12, 5))
        bars = ax.bar(xs, counts, color=bar_colors, edgecolor='#0d1117', linewidth=0.7, zorder=2)

        # Trend line (rolling 3)
        roll3 = pd.Series(counts).rolling(3, min_periods=1).mean().tolist()
        ax.plot(xs, roll3, color='#ff6e40', linewidth=2.5, zorder=3, label='Тренд 3 нед')

        # Annotate all bars
        for i, (x, v) in enumerate(zip(xs, counts)):
            ax.text(x, v + max_c * 0.01, str(v), ha='center', va='bottom',
                    fontsize=8, color='#e6edf3', fontweight='bold')

        # Mark max & min
        idx_max = counts.index(max(counts))
        idx_min = counts.index(min(counts))
        ax.annotate(f'Пик: {counts[idx_max]}',
                    xy=(idx_max, counts[idx_max]), xytext=(idx_max, counts[idx_max] + max_c * 0.08),
                    arrowprops=dict(arrowstyle='->', color='#39d353', lw=1.5),
                    fontsize=8.5, color='#39d353', ha='center', fontweight='bold')
        ax.annotate(f'Мин: {counts[idx_min]}',
                    xy=(idx_min, counts[idx_min]), xytext=(idx_min, counts[idx_min] + max_c * 0.12),
                    arrowprops=dict(arrowstyle='->', color='#f78166', lw=1.5),
                    fontsize=8.5, color='#f78166', ha='center', fontweight='bold')

        ax.set_xticks(xs)
        ax.set_xticklabels([w.replace('20', '') for w in weeks], rotation=40, ha='right', fontsize=8)
        ax.set_ylabel('Уникальных авторов в неделю')
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
        ax.legend(fontsize=8, loc='upper left')
        ax.set_title('2. Размер онлайна (Уникальные шизы за НЕДЕЛЮ)',
                     fontsize=15, fontweight='bold', color='#58a6ff')
        # Stats box
        avg_c = sum(counts) / len(counts)
        ax.text(0.99, 0.97,
                f'Ср. активных: {avg_c:.0f}/нед  |Пик: {max(counts)}  |Мин: {min(counts)}',
                transform=ax.transAxes, fontsize=8, color='#8b949e',
                ha='right', va='top', style='italic')
        plt.tight_layout()
        save_chart(images, '2_wau.png')

def _generate_chart_3(thirty_days_ago, c, images):
    # 3. Матоемкость борды (% постов с матами) — улучшенное
    c.execute('''
        SELECT date(timestamp, 'unixepoch', 'localtime') as d, content
        FROM Posts
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        daily_stats = {}
        swear_roots = ['хуй', 'хуе', 'хуя', 'бля', 'пизд', 'еба', 'пидор', 'гандон', 'шлюх', 'мудак']

        for r in data:
            d = r['d']
            if d not in daily_stats:
                daily_stats[d] = {'total': 0, 'toxic': 0}

            daily_stats[d]['total'] += 1
            content_raw = r['content']
            if content_raw:
                try:
                    content_data = json.loads(content_raw)
                    text = content_data.get('text', '') or content_data.get('caption', '') or ''
                except Exception:
                    text = content_raw

                content_lower = text.lower()
                if any(root in content_lower for root in swear_roots):
                    daily_stats[d]['toxic'] += 1

        plot_data = []
        for d, stats in sorted(daily_stats.items()):
            toxic_percent = (stats['toxic'] / stats['total']) * 100 if stats['total'] > 0 else 0
            plot_data.append({'d': d, 'toxic_percent': toxic_percent})

        df = pd.DataFrame(plot_data)
        fig, ax = plt.subplots(figsize=(12, 5))
        xs3 = list(range(len(df)))
        vals = df['toxic_percent'].tolist()

        ax.fill_between(xs3, vals, color='#ff0055', alpha=0.18, zorder=1)
        ax.plot(xs3, vals, marker='o', markersize=4, color='#ff0055', linewidth=1.5, alpha=0.85, label='Дневной %', zorder=2)

        roll7 = pd.Series(vals).rolling(7, min_periods=1).mean().tolist()
        ax.plot(xs3, roll7, color='#ffcc00', linewidth=2.5, label='Тренд 7 дней', zorder=3)

        avg_tox = sum(vals) / len(vals) if vals else 0
        ax.axhline(avg_tox, color='#8b949e', linestyle='--', linewidth=1.2, label=f'Среднее: {avg_tox:.1f}%', zorder=2)

        idx_max = vals.index(max(vals))
        ax.annotate(f'Пик: {vals[idx_max]:.1f}%',
                    xy=(idx_max, vals[idx_max]), xytext=(idx_max, vals[idx_max] + max(vals)*0.1),
                    arrowprops=dict(arrowstyle='->', color='#ff0055', lw=1.5),
                    fontsize=8.5, color='#ff0055', ha='center', fontweight='bold')

        step3 = max(1, len(df)//10)
        ax.set_xticks(xs3[::step3])
        ax.set_xticklabels(df['d'].tolist()[::step3], rotation=35, ha='right', fontsize=8)
        ax.set_ylabel('% постов с матом')
        ax.set_ylim(0, max(max(vals) * 1.25, 25))
        ax.legend(fontsize=8.5, loc='upper left', framealpha=0.8)
        ax.set_title('3. Матоемкость (% постов с матами, 30д)', fontsize=15, fontweight='bold', color='#ff0055')
        plt.tight_layout()
        save_chart(images, '3_toxicity.png')

def _generate_chart_4(thirty_days_ago, c, images):
    # 4. Топ-10 Главных Шизоидов
    c.execute('''
        SELECT author_id, COUNT(*) as cnt
        FROM Posts
        WHERE author_id IS NOT NULL AND timestamp > ?
        GROUP BY author_id ORDER BY cnt DESC LIMIT 10
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        df['author_name'] = df['author_id'].apply(generate_schizo_name)
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(data=df, y='author_name', x='cnt', hue='author_name', palette="magma", legend=False, ax=ax)
        plt.title('4. Топ-10 Главных Шизоидов (По количеству высеров)', fontsize=16, fontweight='bold', color="#ff9900")
        plt.xlabel('Количество постов')
        plt.ylabel('')
        ax.set_xlim(0, df['cnt'].max() * 1.12)
        for idx, row in df.iterrows():
            ax.text(row['cnt'] + (ax.get_xlim()[1] * 0.01), idx, f"{int(row['cnt'])}",
                    va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
        plt.tight_layout()
        save_chart(images, '4_top_schizos.png')

def _generate_chart_5(thirty_days_ago, c, images):
    # 5. Главные Провокаторы (Топ-5 юзеров, кому больше всего отвечают)
    c.execute('''
        SELECT orig.author_id, COUNT(*) as cnt
        FROM Posts repl
        JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
        WHERE repl.timestamp > ? AND orig.author_id IS NOT NULL
        GROUP BY orig.author_id ORDER BY cnt DESC LIMIT 20
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        df['author_name'] = df['author_id'].apply(generate_schizo_name)
        half5 = len(df) // 2
        df5_l = df.iloc[:half5].reset_index(drop=True)
        df5_r = df.iloc[half5:].reset_index(drop=True)
        fig, (ax5l, ax5r) = plt.subplots(1, 2, figsize=(18, 7))
        for ax5, df5, t5 in [(ax5l, df5_l, 'Топ 1–10'), (ax5r, df5_r, 'Топ 11–20')]:
            sns.barplot(data=df5, y='author_name', x='cnt', hue='author_name',
                        palette='cool', legend=False, ax=ax5)
            ax5.set_xlim(0, df['cnt'].max() * 1.15)
            ax5.set_xlabel('Ответов получено')
            ax5.set_ylabel('')
            ax5.set_title(t5, fontsize=12, color='#33ccff')
            for i, row in df5.iterrows():
                ax5.text(row['cnt'] + df['cnt'].max()*0.01, i, str(int(row['cnt'])),
                         va='center', ha='left', fontsize=8.5, fontweight='bold', color='#ffffff')
        plt.suptitle('5. Главные Байтеры — Топ-20 (Кому больше всего реплаят)',
                     fontsize=15, fontweight='bold', color='#33ccff', y=1.01)
        plt.tight_layout()
        save_chart(images, '5_provocateurs.png', bbox_inches='tight')

def _generate_chart_6(thirty_days_ago, c, images):
    # 6. Гистограмма длины постов — улучшенное
    c.execute('SELECT content FROM Posts WHERE timestamp > ?', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        lengths = []
        for r in data:
            try:
                cd = json.loads(r['content'])
                text = cd.get('text') or cd.get('caption') or ''
                if text:
                    lengths.append(len(text))
            except Exception:
                pass

        if lengths:
            import numpy as _np
            arr = _np.array(lengths)
            arr_clipped = arr[arr < 800]  # tighter clip to show detail

            fig, ax = plt.subplots(figsize=(12, 5))
            # Zone fills
            ax.axvspan(0,   20,  alpha=0.08, color='#ff3366', zorder=0)
            ax.axvspan(20,  150, alpha=0.06, color='#58a6ff', zorder=0)
            ax.axvspan(150, 800, alpha=0.06, color='#39d353', zorder=0)

            n, bins, patches = ax.hist(arr_clipped, bins=60, color='#cc00ff',
                                       edgecolor='#0d1117', linewidth=0.4, zorder=2)

            # Color bins by zone
            for patch, left in zip(patches, bins[:-1]):
                if left < 20:  patch.set_facecolor('#ff3366')
                elif left < 150: patch.set_facecolor('#9933ff')
                else: patch.set_facecolor('#39d353')

            # Percentile lines
            p50  = _np.percentile(arr, 50)
            p75  = _np.percentile(arr, 75)
            p90  = _np.percentile(arr, 90)
            for pv, label, col in [(p50, f'Медиан\n{p50:.0f}сим', '#ffcc00'),
                                   (p75, f'75th\n{p75:.0f}сим', '#ff9933'),
                                   (p90, f'90th\n{p90:.0f}сим', '#ff3366')]:
                if pv < 800:
                    ax.axvline(pv, color=col, linestyle='--', linewidth=1.3, alpha=0.85, zorder=3)
                    ax.text(pv + 4, ax.get_ylim()[1] * 0.85, label,
                            color=col, fontsize=7.5, va='top', fontweight='bold')

            # Zone labels
            ax.text(10,  ax.get_ylim()[1] * 0.92, 'Одноклет\n<20', color='#ff3366',
                    fontsize=7, ha='center', fontweight='bold')
            ax.text(310, ax.get_ylim()[1] * 0.92, 'Пасты\n>150', color='#39d353',
                    fontsize=7, ha='center', fontweight='bold')

            # Stats box
            one_liners = int((arr < 20).sum())
            pastas     = int((arr > 300).sum())
            pct_one    = 100 * one_liners / len(arr)
            pct_pasta  = 100 * pastas / len(arr)
            stats_txt  = (f'Всего: {len(arr):,}  |Одноклет: {pct_one:.1f}%  '
                          f'|Пасты: {pct_pasta:.1f}%  |Ср.: {arr.mean():.0f}с')
            ax.text(0.99, 0.97, stats_txt, transform=ax.transAxes,
                    fontsize=8, color='#8b949e', ha='right', va='top', style='italic')

            ax.set_xlabel('Длина текста (символы)')
            ax.set_ylabel('Количество постов')
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
            ax.set_title('6. Формат общения (Длина постов, 30д)',
                         fontsize=15, fontweight='bold', color='#cc00ff')
            plt.tight_layout()
            save_chart(images, '6_post_length.png')

def _generate_chart_7(thirty_days_ago, c, images):
    # 7. Клуб Полуночников (Ночная vs Дневная активность)
    c.execute('''
        SELECT
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as night_posts,
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) NOT BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as day_posts,
            COUNT(*) as total
        FROM Posts WHERE timestamp > ?
    ''', (thirty_days_ago,))
    r7 = c.fetchone()
    
    c.execute('''
        SELECT author_id, COUNT(*) as cnt
        FROM Posts
        WHERE timestamp > ? AND cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) BETWEEN 1 AND 6
              AND author_id IS NOT NULL AND author_id != 0
        GROUP BY author_id ORDER BY cnt DESC LIMIT 5
    ''', (thirty_days_ago,))
    top_owls = c.fetchall()

    if r7:
        fig, (ax_pie, ax_bar) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={'width_ratios': [1, 1.4]})
        night_p = r7['night_posts'] or 0
        day_p = r7['day_posts'] or 0
        
        wedges, texts, autotexts = ax_pie.pie(
            [night_p, day_p], labels=['Ночной сыч\n(01:00–06:00)', 'Дневной анон\n(06:00–01:00)'],
            autopct='%1.1f%%', startangle=140,
            colors=['#7928ca', '#ffa657'],
            wedgeprops=dict(width=0.52, edgecolor='#0d1117', linewidth=2),
            pctdistance=0.72
        )
        for at in autotexts:
            at.set_color('#ffffff')
            at.set_fontweight('bold')
            at.set_fontsize(11)
        ax_pie.set_title('7. Клуб Полуночников (30д)\nДоля ночного контента', fontsize=13, fontweight='bold', color='#a371f7')

        if top_owls:
            owl_names = [generate_schizo_name(r['author_id']).split('(')[0].strip() for r in top_owls]
            owl_cnts = [r['cnt'] for r in top_owls]
            owl_names.reverse()
            owl_cnts.reverse()
            bars = ax_bar.barh(owl_names, owl_cnts, color='#8957e5', edgecolor='#0d1117', linewidth=0.6)
            for bar, val in zip(bars, owl_cnts):
                ax_bar.text(bar.get_width() + max(owl_cnts)*0.015, bar.get_y() + bar.get_height()/2,
                            f'{val:,} ночных постов', va='center', fontsize=9, color='#e6edf3', fontweight='bold')
            ax_bar.set_title('Главные ночные шизоиды (Топ-5)', fontsize=12, fontweight='bold', color='#d2a8ff')
            ax_bar.set_xlim(0, max(owl_cnts) * 1.28)
            ax_bar.set_xlabel('Постов в интервале 01:00–06:00')
            ax_bar.xaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
        plt.tight_layout()
        save_chart(images, '7_night_owls.png', bbox_inches='tight')

def _generate_chart_8(thirty_days_ago, c, images):
    # 8. Картинко-дрочеры (Медиа vs Текст с детализацией)
    c.execute('''
        SELECT content FROM Posts WHERE timestamp > ? AND content IS NOT NULL
    ''', (thirty_days_ago,))
    rows = c.fetchall()
    if rows:
        counts = {'text': 0, 'photo': 0, 'video': 0, 'animation': 0, 'sticker': 0, 'other': 0}
        for r in rows:
            raw = r['content']
            try:
                d = json.loads(raw)
                t = d.get('type', 'text')
                if t in counts:
                    counts[t] += 1
                else:
                    counts['other'] += 1
            except Exception:
                counts['text'] += 1
        
        fig, (ax8_pie, ax8_bar) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={'width_ratios': [1, 1.4]})
        media_total = sum(v for k, v in counts.items() if k != 'text')
        text_total = counts['text']
        
        wedges, texts, autotexts = ax8_pie.pie(
            [text_total, media_total], labels=['Текст\n(чистый пост)', 'Медиа\n(картинка/видео)'],
            autopct='%1.1f%%', startangle=120,
            colors=['#388bfd', '#f778ba'],
            wedgeprops=dict(width=0.52, edgecolor='#0d1117', linewidth=2),
            pctdistance=0.72
        )
        for at in autotexts:
            at.set_color('#ffffff')
            at.set_fontweight('bold')
            at.set_fontsize(11)
        ax8_pie.set_title('8. Картинко-дрочеры (30д)\nТекст vs Медиаконтент', fontsize=13, fontweight='bold', color='#f778ba')

        labels_map = {'photo': 'Фотографии', 'video': 'Видеофайлы', 'animation': 'GIF / WebM', 'sticker': 'Стикеры', 'text': 'Текст', 'other': 'Прочее'}
        sorted_types = sorted(counts.items(), key=lambda x: x[1], reverse=False)
        types_ru = [labels_map.get(k, k) for k, v in sorted_types]
        types_val = [v for k, v in sorted_types]
        
        cmap_m = plt.get_cmap('spring')
        colors_m = [cmap_m(0.2 + 0.7 * i / len(types_val)) for i in range(len(types_val))]
        bars8 = ax8_bar.barh(types_ru, types_val, color=colors_m, edgecolor='#0d1117', linewidth=0.6)
        max_v = max(types_val) or 1
        tot = sum(types_val) or 1
        for bar, v in zip(bars8, types_val):
            ax8_bar.text(bar.get_width() + max_v * 0.015, bar.get_y() + bar.get_height()/2,
                         f'{v:,} ({100*v/tot:.1f}%)', va='center', fontsize=9, color='#e6edf3', fontweight='bold')
        ax8_bar.set_title('Детализация типов контента', fontsize=12, fontweight='bold', color='#ffa657')
        ax8_bar.set_xlim(0, max_v * 1.28)
        ax8_bar.xaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
        plt.tight_layout()
        save_chart(images, '8_media_breakdown.png', bbox_inches='tight')

def _generate_chart_9(thirty_days_ago, c, images):
    # 9. Уровень Дискуссии (Диалоги vs Монологи и Latency ответов)
    c.execute('''
        SELECT
            SUM(CASE WHEN reply_to_post_num IS NOT NULL THEN 1 ELSE 0 END) as replies,
            SUM(CASE WHEN reply_to_post_num IS NULL THEN 1 ELSE 0 END) as singles,
            COUNT(*) as total
        FROM Posts WHERE timestamp > ?
    ''', (thirty_days_ago,))
    r9 = c.fetchone()
    if r9:
        replies_cnt = r9['replies'] or 0
        singles_cnt = r9['singles'] or 0
        
        c.execute('''
            SELECT (repl.timestamp - orig.timestamp) as delta_sec
            FROM Posts repl
            JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
            WHERE repl.timestamp > ? AND repl.timestamp >= orig.timestamp
        ''', (thirty_days_ago,))
        deltas = [row['delta_sec'] for row in c.fetchall()]
        
        fig, (ax9_pie, ax9_bar) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={'width_ratios': [1, 1.4]})
        
        wedges, texts, autotexts = ax9_pie.pie(
            [replies_cnt, singles_cnt], labels=['Диалоги\n(ответ на пост)', 'Монологи\n(крик в пустоту)'],
            autopct='%1.1f%%', startangle=140,
            colors=['#3fb950', '#8b949e'],
            wedgeprops=dict(width=0.52, edgecolor='#0d1117', linewidth=2),
            pctdistance=0.72
        )
        for at in autotexts:
            at.set_color('#ffffff')
            at.set_fontweight('bold')
            at.set_fontsize(11)
        ax9_pie.set_title('9. Уровень Дискуссии (30д)\nДиалоги vs Одиночные посты', fontsize=13, fontweight='bold', color='#3fb950')

        if deltas:
            import numpy as _np
            d_arr = _np.array(deltas)
            b_fast = int((d_arr <= 120).sum())
            b_quick = int(((d_arr > 120) & (d_arr <= 900)).sum())
            b_mid = int(((d_arr > 900) & (d_arr <= 3600)).sum())
            b_slow = int(((d_arr > 3600) & (d_arr <= 21600)).sum())
            b_late = int((d_arr > 21600).sum())
            
            d_labels = ['< 2 мин (Мгновенно)', '2–15 мин (Быстро)', '15–60 мин (Живой тред)', '1–6 часов (Слоупоки)', '> 6 часов (Некробамп)']
            d_vals = [b_fast, b_quick, b_mid, b_slow, b_late]
            d_labels.reverse()
            d_vals.reverse()
            
            cmap_d = plt.get_cmap('viridis')
            colors_d = [cmap_d(0.25 + 0.7 * i / len(d_vals)) for i in range(len(d_vals))]
            bars9 = ax9_bar.barh(d_labels, d_vals, color=colors_d, edgecolor='#0d1117', linewidth=0.6)
            max_dv = max(d_vals) or 1
            tot_d = sum(d_vals) or 1
            for bar, v in zip(bars9, d_vals):
                ax9_bar.text(bar.get_width() + max_dv * 0.015, bar.get_y() + bar.get_height()/2,
                             f'{v:,} ({100*v/tot_d:.1f}%)', va='center', fontsize=9, color='#e6edf3', fontweight='bold')
            ax9_bar.set_title('Скорость ответа на реплаи (Latency)', fontsize=12, fontweight='bold', color='#7ee787')
            ax9_bar.set_xlim(0, max_dv * 1.30)
            ax9_bar.xaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f'{int(val):,}'))
            
        plt.tight_layout()
        save_chart(images, '9_dialogue_level.png', bbox_inches='tight')

def _generate_chart_10(thirty_days_ago, c, images):
    # 10. Тепловая карта активности (Heatmap)
    c.execute('''
        SELECT cast(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as w,
               cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
               COUNT(*) as cnt
        FROM Posts
        WHERE timestamp > ?
        GROUP BY w, h
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        heatmap_data = df.pivot(index="w", columns="h", values="cnt").fillna(0)
        # Ensure all 24 hours are present in columns
        heatmap_data = heatmap_data.reindex(columns=range(24), fill_value=0)
        # Ensure all weekdays are present in index and reorder (1=Mon, 2=Tue... 6=Sat, 0=Sun)
        heatmap_data = heatmap_data.reindex(index=[1, 2, 3, 4, 5, 6, 0], fill_value=0)
        heatmap_data.index = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

        fig, ax = plt.subplots(figsize=(12, 6))
        sns.heatmap(heatmap_data, cmap="inferno", linewidths=.5, ax=ax)
        plt.title('10. Циркадные ритмы Анона (Активность по часам/дням)', fontsize=16, fontweight='bold', color="#ffaa00")
        plt.xlabel('Час (МСК)')
        plt.ylabel('День недели')
        plt.tight_layout()
        save_chart(images, '10_heatmap.png')

def _generate_chart_11(thirty_days_ago, c, images):
    edges_data = None
    # 11. Граф Социального Пузыря (Эхо-камеры) — улучшенное
    try:
        c.execute('''
            SELECT repl.author_id as replier, orig.author_id as original, COUNT(*) as weight
            FROM Posts repl
            JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
            WHERE repl.timestamp > ? AND repl.author_id IS NOT NULL AND orig.author_id IS NOT NULL
            GROUP BY replier, original
        ''', (thirty_days_ago,))
        edges_data = c.fetchall()
        if edges_data:
            import networkx as nx
            G = nx.Graph()
            for edge in edges_data:
                u, v, w = edge['replier'], edge['original'], edge['weight']
                if u == v: continue
                if G.has_edge(u, v):
                    G[u][v]['weight'] += w
                else:
                    G.add_edge(u, v, weight=w)

            if len(G) > 0:
                # Take top-60 by degree — fewer nodes = better spread
                top_nodes = [node for node, degree in
                             sorted(G.degree(), key=lambda x: x[1], reverse=True)[:60]]
                G_sub = G.subgraph(top_nodes).copy()

                # Prune weak edges to reduce visual noise
                weak_edges = [(u, v) for u, v, d in G_sub.edges(data=True) if d['weight'] < 2]
                G_sub2 = G_sub.copy()
                G_sub2.remove_edges_from(weak_edges)

                communities = nx.community.louvain_communities(G_sub2, seed=42)
                community_map = {}
                for i, comm in enumerate(communities):
                    for node in comm:
                        community_map[node] = i

                node_colors = [community_map.get(node, 0) for node in G_sub2.nodes()]
                # Node size = degree
                node_sizes = [max(40, G_sub2.degree(n) * 25) for n in G_sub2.nodes()]
                edge_weights_raw = [d['weight'] for _, _, d in G_sub2.edges(data=True)]
                max_ew = max(edge_weights_raw) if edge_weights_raw else 1
                edge_widths = [0.4 + 2.0 * (w / max_ew) for w in edge_weights_raw]

                fig, ax = plt.subplots(figsize=(12, 10))
                ax.set_facecolor('#0d1117')
                # k=0.5 for better spread, rescale to fill canvas
                pos = nx.spring_layout(G_sub2, k=0.5, iterations=100, seed=42)
                nx.draw_networkx_nodes(G_sub2, pos, node_size=node_sizes,
                                       node_color=node_colors, cmap=plt.cm.tab20,
                                       ax=ax, alpha=0.92)
                nx.draw_networkx_edges(G_sub2, pos, width=edge_widths,
                                       alpha=0.25, edge_color='#58a6ff', ax=ax)
                # Label only top-15 by degree
                top15 = sorted(G_sub2.nodes(), key=lambda n: G_sub2.degree(n), reverse=True)[:15]
                labels = {n: generate_schizo_name(n).split(' ')[0] for n in top15}
                nx.draw_networkx_labels(G_sub2, pos, labels, font_size=6.5,
                                        font_color='#e6edf3', ax=ax)
                # Community count annotation
                ax.text(0.01, 0.01,
                        f'Кластеров: {len(communities)}  |Узлов: {len(G_sub2)}  |Связей: {G_sub2.number_of_edges()}',
                        transform=ax.transAxes, fontsize=8, color='#8b949e', va='bottom')
                plt.title('11. Граф Социального Пузыря (Эхо-камеры)\n'
                         'Цвет = кластер, размер = связность, подписаны топ-15',
                         fontsize=14, fontweight='bold', color='#00ffcc', pad=10)
                ax.axis('off')
                plt.tight_layout()
                save_chart(images, '11_echo_chambers.png')
    except Exception as e:
        print(f"Error Chart 11: {e}")
    return edges_data

def _generate_chart_12(edges_data, images):
    # 12. Топ-10 Хабов Внимания (PageRank Centrality)
    try:
        if edges_data:
            import networkx as nx
            DiG = nx.DiGraph()
            for edge in edges_data:
                u, v, w = edge['replier'], edge['original'], edge['weight']
                if u == v: continue
                DiG.add_edge(u, v, weight=w)

            if len(DiG) > 0:
                pagerank_scores = nx.pagerank(DiG, weight='weight')
                sorted_pr = sorted(pagerank_scores.items(), key=lambda x: x[1], reverse=True)[:10]

                df_pr = pd.DataFrame(sorted_pr, columns=['author_id', 'pagerank'])
                df_pr['author_name'] = df_pr['author_id'].apply(generate_schizo_name)

                fig, ax = plt.subplots(figsize=(10, 5))
                sns.barplot(data=df_pr, y='author_name', x='pagerank', hue='author_name', palette="cool", legend=False, ax=ax)
                plt.title('12. Топ-10 Хабов Внимания (PageRank)', fontsize=16, fontweight='bold', color="#ff00ff")
                plt.xlabel('Влияние (PageRank score)')
                plt.ylabel('')
                ax.set_xlim(0, df_pr['pagerank'].max() * 1.15)
                for idx, row in df_pr.iterrows():
                    ax.text(row['pagerank'] + (ax.get_xlim()[1] * 0.01), idx, f"{row['pagerank']:.4f}",
                            va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
                plt.tight_layout()
                save_chart(images, '12_pagerank.png')
    except Exception as e:
        print(f"Error Chart 12: {e}")

def _generate_chart_13(edges_data, images):
    # 13. Коэффициент Взаимного Дроча (Circlejerk Index)
    try:
        if edges_data:
            mutuals = {}
            for edge in edges_data:
                u, v, w = edge['replier'], edge['original'], edge['weight']
                if u == v: continue
                pair = tuple(sorted((u, v)))
                if pair not in mutuals:
                    mutuals[pair] = {u: 0, v: 0}
                mutuals[pair][u] += w

            mutual_list = []
            for pair, weights in mutuals.items():
                u, v = pair
                w_u = weights.get(u, 0)
                w_v = weights.get(v, 0)
                reciprocity = 2 * min(w_u, w_v)
                if reciprocity > 0:
                    mutual_list.append((u, v, reciprocity))

            if mutual_list:
                sorted_mutual = sorted(mutual_list, key=lambda x: x[2], reverse=True)[:10]
                plot_data = []
                for u, v, rec in sorted_mutual:
                    name_u = generate_schizo_name(u)
                    name_v = generate_schizo_name(v)
                    plot_data.append({'pair': f"{name_u} & {name_v}", 'score': rec})

                df_mut = pd.DataFrame(plot_data)
                fig, ax = plt.subplots(figsize=(12, 8))
                sns.barplot(data=df_mut, y='pair', x='score', hue='pair', palette="spring", legend=False, ax=ax)
                plt.title('13. Топ-10 Взаимных Перепихонов (Circlejerk)', fontsize=16, fontweight='bold', color="#00ff66")
                plt.xlabel('Количество взаимных ответов друг другу')
                plt.ylabel('')
                ax.set_xlim(0, df_mut['score'].max() * 1.12)
                for idx, row in df_mut.iterrows():
                    ax.text(row['score'] + (ax.get_xlim()[1] * 0.01), idx, f"{int(row['score'])}",
                            va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
                plt.tight_layout()
                save_chart(images, '13_circlejerk.png')
    except Exception as e:
        print(f"Error Chart 13: {e}")

def _generate_chart_14(thirty_days_ago, c, images):
    # 14. Сессионный Анализ (Длина сессий)
    try:
        c.execute('''
            SELECT author_id, timestamp
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL
            ORDER BY author_id, timestamp
        ''', (thirty_days_ago,))
        posts_timeline = c.fetchall()
        if posts_timeline:
            user_posts = {}
            for r in posts_timeline:
                uid = r['author_id']
                ts = r['timestamp']
                if uid not in user_posts:
                    user_posts[uid] = []
                user_posts[uid].append(ts)

            session_durations = []
            for uid, times in user_posts.items():
                if len(times) == 1:
                    session_durations.append(1.0)
                    continue

                start_ts = times[0]
                prev_ts = times[0]
                for ts in times[1:]:
                    if ts - prev_ts > 900:
                        duration = max((prev_ts - start_ts) / 60.0, 1.0)
                        session_durations.append(duration)
                        start_ts = ts
                    prev_ts = ts
                duration = max((prev_ts - start_ts) / 60.0, 1.0)
                session_durations.append(duration)

            if session_durations:
                import numpy as _np
                df_sess = pd.DataFrame({'duration': session_durations})
                flash_count = int((df_sess['duration'] < 1).sum())
                df_sess = df_sess[(df_sess['duration'] >= 1) & (df_sess['duration'] < 180)]
                arr_s = df_sess['duration'].values

                fig, ax = plt.subplots(figsize=(11, 5))

                # Zone fills
                ax.axvspan(0,  5,   alpha=0.10, color='#58a6ff', zorder=0)  # flash
                ax.axvspan(5,  30,  alpha=0.07, color='#39d353', zorder=0)  # normal
                ax.axvspan(30, 180, alpha=0.07, color='#ffa657', zorder=0)  # deep dive

                n, bins, patches = ax.hist(arr_s, bins=40, color='#ff9933',
                                           edgecolor='#0d1117', linewidth=0.4, zorder=2)
                # Color bins by zone
                for patch, left in zip(patches, bins[:-1]):
                    if left < 5:  patch.set_facecolor('#58a6ff')
                    elif left < 30: patch.set_facecolor('#ff9933')
                    else: patch.set_facecolor('#ffa657')

                # Percentile lines
                p50 = _np.percentile(arr_s, 50)
                p90 = _np.percentile(arr_s, 90)
                for pv, label, col in [(p50, f'Медиан\n{p50:.0f}мин', '#ffcc00'),
                                       (p90, f'90th\n{p90:.0f}мин', '#ff3366')]:
                    ax.axvline(pv, color=col, linestyle='--', linewidth=1.5, alpha=0.9, zorder=3)
                    ax.text(pv + 1, ax.get_ylim()[1] * 0.82, label,
                            color=col, fontsize=8, va='top', fontweight='bold')

                # Zone labels
                ax.text(2.5, ax.get_ylim()[1]*0.92, 'Мгнов\n<5м', color='#58a6ff',
                        fontsize=7, ha='center', fontweight='bold')
                ax.text(17,  ax.get_ylim()[1]*0.92, 'Норма', color='#39d353',
                        fontsize=7, ha='center', fontweight='bold')
                ax.text(100, ax.get_ylim()[1]*0.92, 'Длинные залипания', color='#ffa657',
                        fontsize=7, ha='center', fontweight='bold')

                # Stats box — include original flash count
                flash_pct  = 100 * (arr_s < 5).sum() / len(arr_s)
                deep_pct   = 100 * (arr_s > 30).sum() / len(arr_s)
                total_sess = len(arr_s) + flash_count
                stats_txt  = (f'Всего: {total_sess:,}  |Мгнов.<1м: {flash_count:,}  '
                              f'|Длинных: {deep_pct:.1f}%  |Ср.: {arr_s.mean():.1f}мин')
                ax.text(0.99, 0.97, stats_txt, transform=ax.transAxes,
                        fontsize=8, color='#8b949e', ha='right', va='top', style='italic')

                ax.set_xlabel('Длительность сессии (минуты, пауза 15 мин = новая сессия)')
                ax.set_ylabel('Количество сессий')
                ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
                ax.set_title('14. Длина непрерывного залипания (Сессии, 30д)',
                             fontsize=15, fontweight='bold', color='#ff9933')
                plt.tight_layout()
                save_chart(images, '14_sessions.png')
    except Exception as e:
        print(f"Error Chart 14: {e}")


def _clean_text_local(raw_content):
    if not raw_content:
        return ""
    try:
        content_dict = json.loads(raw_content)
        text = content_dict.get('text', '') or content_dict.get('caption', '') or ''
    except Exception:
        text = raw_content
    if not text:
        return ""
    text_clean = re.sub(r'<[^>]+>', '', text)
    return text_clean

# Expand stop words dynamically

RADAR_STOP_WORDS = RU_STOP.union({
    'prefixes', 'prefix', 'injections', 'injection', 'signatures', 'signature',
    'info', 'entry', 'exit', 'take', 'profit', 'zone', 'price', 'reason',
    'buy', 'sell', 'usdt', 'btc', 'eth', 'sol', 'xmr', 'ltc', 'trx', 'trc',
    'trc20', 'ton', 'sim', 'pnl', 'gross', 'net', 'limit', 'stop', 'cringe', 'report'
})


def _get_word_counts(posts_list):
    from collections import Counter
    counts = Counter()
    for row in posts_list:
        # 1. Skip system posts
        if row.get('author_id') in (0, 1163970492):
            continue

        text = _clean_text_local(row['content'])

        # 2. Skip logs and reports structurally
        if text.count('|') >= 3:
            continue
        if '[INFO]' in text or '[DEBUG]' in text or '[ERROR]' in text:
            continue
        if 'ChatGPT Cringe Report' in text or 'нелепых и шаблонных фразах' in text:
            continue

        tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ]{4,}', text.lower())
        for t in tokens:
            if t not in RADAR_STOP_WORDS:
                counts[t] += 1
    return counts


def _generate_chart_15(c, images):
    # 15. Мем-Радар: Взлетающие Тренды (Rising Keywords)
    try:
        now_ts = time.time()
        seven_days_ago = now_ts - (7 * 24 * 3600)
        fourteen_days_ago = now_ts - (14 * 24 * 3600)

        c.execute("SELECT content, author_id FROM Posts WHERE timestamp > ?", (seven_days_ago,))
        this_week_posts = c.fetchall()

        c.execute("SELECT content, author_id FROM Posts WHERE timestamp BETWEEN ? AND ?", (fourteen_days_ago, seven_days_ago))
        last_week_posts = c.fetchall()

        this_week_counts = _get_word_counts(this_week_posts)
        last_week_counts = _get_word_counts(last_week_posts)

        rising_words = []
        for word, c1 in this_week_counts.items():
            c2 = last_week_counts.get(word, 0)
            if c1 >= 5 and c1 > c2:
                pct_change = ((c1 - c2) / c2) * 100 if c2 > 0 else c1 * 100
                rising_words.append({'word': word, 'c1': c1, 'c2': c2, 'change': pct_change})

        rising_words = sorted(rising_words, key=lambda x: x['change'], reverse=True)[:20]

        if rising_words:
            df_radar = pd.DataFrame(rising_words)
            df_left = df_radar.iloc[:10].reset_index(drop=True)
            df_right = df_radar.iloc[10:20].reset_index(drop=True)

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))

            # Left subplot (Top 1-10)
            if not df_left.empty:
                sns.barplot(data=df_left, x='change', y='word', hue='word', palette="Reds_r", legend=False, ax=ax1)
                ax1.set_title('Топ 1–10 (Наибольший взлет)', fontsize=12, fontweight='bold', color="#ff3333")
                ax1.set_xlabel('Прирост (%)')
                ax1.set_ylabel('')
                for idx, row in df_left.iterrows():
                    ax1.text(row['change'] + (ax1.get_xlim()[1]*0.01), idx, f"+{int(row['change'])}%",
                            va='center', fontsize=9, fontweight='bold', color="#ff3333")

            # Right subplot (Top 11-20)
            if not df_right.empty:
                sns.barplot(data=df_right, x='change', y='word', hue='word', palette="Oranges_r", legend=False, ax=ax2)
                ax2.set_title('Топ 11–20 (Умеренный взлет)', fontsize=12, fontweight='bold', color="#ff9933")
                ax2.set_xlabel('Прирост (%)')
                ax2.set_ylabel('')
                for idx, row in df_right.iterrows():
                    ax2.text(row['change'] + (ax2.get_xlim()[1]*0.01), idx, f"+{int(row['change'])}%",
                            va='center', fontsize=9, fontweight='bold', color="#ff9933")

            plt.suptitle('15. Мем-Радар: Взлетающие Тренды (Прирост за неделю)', fontsize=16, fontweight='bold', color="#ffaa00", y=0.96)
            plt.tight_layout(rect=[0, 0, 1, 0.95])
            save_chart(images, '15_autocorrelation.png')
    except Exception as e:
        print(f"Error Chart 15: {e}")

def _generate_chart_16(thirty_days_ago, c, images):
    # 16. Частотный Шитпост-Словарь (Топ-15 Слов)
    try:
        from collections import Counter
        c.execute('''
            SELECT content FROM Posts
            WHERE timestamp > ? AND content IS NOT NULL
        ''', (thirty_days_ago,))
        word_data = c.fetchall()
        if word_data:
            ru_stop = {
                'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты',
                'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'уже',
                'до', 'этого', 'этой', 'эти', 'эту', 'это', 'тот', 'где', 'кто', 'он', 'мы', 'быть', 'был', 'была', 'были', 'было', 'есть',
                'если', 'или', 'ком', 'всех', 'них', 'этот', 'чтобы', 'для', 'без', 'через', 'после', 'потому', 'этом', 'им', 'ей',
                'про', 'почему', 'зачем', 'очень', 'просто', 'тут', 'там', 'когда', 'будет', 'даже', 'всегда', 'тоже',
                'какой', 'какая', 'какие', 'свои', 'свой', 'своих', 'под', 'над', 'перед', 'при', 'всего', 'всем', 'всеми', 'тебе', 'вас',
                'как', 'так', 'это', 'был', 'была', 'будет', 'мне', 'меня', 'тебе', 'тебя', 'свой', 'свои', 'своих',
                'все', 'всё', 'всех', 'всем', 'очень', 'просто', 'было', 'были', 'быть', 'один', 'два', 'три', 'когда',
                'если', 'или', 'нет', 'да', 'уже', 'еще', 'ещё', 'только', 'вот', 'этот', 'эта', 'эти', 'это',
                'можно', 'надо', 'может', 'потом', 'больше', 'вообще', 'себя', 'которые', 'который', 'себе', 'такой', 'пока', 'лучше', 'того', 'сейчас', 'здесь', 'быть', 'было', 'будет', 'если', 'этого', 'очень', 'просто', 'чтобы',
                'какой', 'какие', 'какая', 'почему', 'зачем', 'хотя', 'тоже', 'даже', 'тут', 'там', 'где', 'когда', 'кто', 'что', 'как', 'потому',
                'также', 'такое', 'теперь', 'нужно', 'только', 'будто', 'каждый', 'будто', 'очень', 'просто', 'чтобы', 'после', 'через', 'около', 'возле', 'снова', 'опять', 'назад', 'перед', 'один', 'когда',
                # URLs, tech tags, bot specifics
                'http', 'https', 'www', 'com', 'ru', 'org', 'net', 'href', 'html', 'code', 'emoji', 'span', 'div', 'class', 'style', 'br', 'li', 'ul', 'ol', 'pre', 'img', 'src', 'width', 'height', 'alt', 'title', 'target', 'blank', 'rel', 'noopener', 'noreferrer', 'data',
                'tgach', 'тгач', 'chatbot', 'dvach', 'dvachbot', 'bot', 'id', 'user', 'author', 'posts', 'post', 'thread', 'board', 'text', 'type', 'message', 'telegram', 'entities', 'url'
            }

            words_list = []
            for r in word_data:
                content_raw = r['content']
                if not content_raw:
                    continue
                try:
                    content_dict = json.loads(content_raw)
                    text = content_dict.get('text', '') or content_dict.get('caption', '') or ''
                except Exception:
                    text = content_raw
                if not text:
                    continue

                # Strip HTML tags
                text_clean = re.sub(r'<[^>]+>', '', text)

                # Tokenize cyrillic and latin words
                tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ]+', text_clean.lower())
                for token in tokens:
                    if len(token) > 3 and token not in ru_stop:
                        words_list.append(token)

            counter = Counter(words_list)
            top_words = counter.most_common(30)
            if top_words:
                df_words = pd.DataFrame(top_words, columns=['Слово', 'Частота'])

                fig, ax = plt.subplots(figsize=(10, 10))
                sns.barplot(data=df_words, x='Частота', y='Слово', hue='Слово', palette="plasma", legend=False, ax=ax)
                plt.title('16. Частотный Шитпост-Словарь (Топ-30 Слов)', fontsize=16, fontweight='bold', color="#ff33cc")
                plt.xlabel('Количество упоминаний за 30 дней')
                plt.ylabel('')
                ax.set_xlim(0, df_words['Частота'].max() * 1.12)
                for idx, row in df_words.iterrows():
                    ax.text(row['Частота'] + (ax.get_xlim()[1] * 0.01), idx, f"{int(row['Частота'])}",
                            va='center', ha='left', fontsize=9, fontweight='bold', color="#ffffff")
                plt.tight_layout()
                save_chart(images, '16_top_words.png')
    except Exception as e:
        print(f"Error Chart 16: {e}")

def _generate_chart_17(thirty_days_ago, c, images):
    # 17. Индекс Токсичности (Сентимент)
    try:
        c.execute('''
            SELECT date(timestamp, 'unixepoch', 'localtime') as d, content
            FROM Posts
            WHERE timestamp > ? AND content IS NOT NULL
        ''', (thirty_days_ago,))
        sentiment_posts = c.fetchall()
        if sentiment_posts:
            pos_words = {'база', 'базирован', 'красавчик', 'хорош', 'круто', 'ахуенно', 'охуенно', 'люблю', 'спасибо', 'четко', 'класс', 'лучший', 'добро'}
            neg_words = {'говно', 'хуйня', 'пидор', 'сука', 'урод', 'ненавижу', 'смерть', 'боль', 'плохо', 'худший', 'тупой', 'дебил', 'долбоеб', 'даун', 'мразь', 'ебать', 'хуй', 'бля', 'пиздец'}

            daily_sent = {}
            for r in sentiment_posts:
                d = r['d']
                if d not in daily_sent:
                    daily_sent[d] = []

                try:
                    content_dict = json.loads(r['content'])
                    text = (content_dict.get('text') or content_dict.get('caption') or '').lower()
                except:
                    text = (r['content'] or '').lower()

                if not text:
                    continue

                words = text.split()
                score = 0
                for w in words:
                    w_clean = w.strip('.,!?-()":;')
                    if w_clean in pos_words:
                        score += 1
                    elif w_clean in neg_words:
                        score -= 1
                daily_sent[d].append(score)

            plot_data = []
            for d, scores in sorted(daily_sent.items()):
                avg_score = sum(scores) / len(scores) if scores else 0.0
                plot_data.append({'d': d, 'sentiment': avg_score})

            if plot_data:
                df_sent = pd.DataFrame(plot_data)
                fig, ax = plt.subplots(figsize=(10, 5))
                xs17 = list(range(len(df_sent)))
                vals17 = df_sent['sentiment'].tolist()
                ax.plot(xs17, vals17, marker='o', color='#aaaaaa', linewidth=1.5, zorder=3)
                ax.fill_between(xs17, vals17, 0, where=[v >= 0 for v in vals17], color='#33cc66', alpha=0.3, label='База')
                ax.fill_between(xs17, vals17, 0, where=[v < 0 for v in vals17], color='#ff3333', alpha=0.3, label='Токсик')
                ax.axhline(0, color='#555555', linewidth=1, linestyle='--')
                step17 = max(1, len(df_sent)//10)
                ax.set_xticks(xs17[::step17])
                ax.set_xticklabels(df_sent['d'].tolist()[::step17], rotation=45, ha='right', fontsize=7)
                ax.legend(fontsize=9)
                plt.title('17. Индекс Токсичности (Двачевский сентимент)', fontsize=16, fontweight='bold', color='#ff3333')
                plt.ylabel('Средний сентимент (выше = база, ниже = токсик)')
                plt.tight_layout()
                save_chart(images, '17_sentiment.png')
    except Exception as e:
        print(f"Error Chart 17: {e}")

def _generate_chart_18(thirty_days_ago, c, images):
    # 18. Лексическое Разнообразие (MSTTR)
    try:
        c.execute('''
            SELECT author_id, content
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND content IS NOT NULL
        ''', (thirty_days_ago,))
        ttr_data = c.fetchall()
        if ttr_data:
            user_texts = {}
            for r in ttr_data:
                uid = r['author_id']
                try:
                    content_dict = json.loads(r['content'])
                    text = content_dict.get('text') or content_dict.get('caption') or ''
                except:
                    text = r['content'] or ''
                if text:
                    if uid not in user_texts:
                        user_texts[uid] = []
                    user_texts[uid].append(text.lower())

            sorted_users = sorted(user_texts.items(), key=lambda x: len(x[1]), reverse=True)[:10]

            msttr_results = []
            for uid, texts in sorted_users:
                full_text = " ".join(texts)
                words = [w.strip('.,!?-()":;') for w in full_text.split() if w.strip('.,!?-()":;')]

                segment_size = 100
                segments = [words[i:i + segment_size] for i in range(0, len(words), segment_size) if len(words[i:i + segment_size]) == segment_size]

                if segments:
                    ttrs = []
                    for seg in segments:
                        ttrs.append(len(set(seg)) / segment_size)
                    msttr = sum(ttrs) / len(ttrs)
                else:
                    msttr = len(set(words)) / len(words) if words else 0.0

                msttr_results.append((uid, msttr))

            if msttr_results:
                df_ttr = pd.DataFrame(msttr_results, columns=['author_id', 'msttr'])
                df_ttr['author_name'] = df_ttr['author_id'].apply(generate_schizo_name)

                fig, ax = plt.subplots(figsize=(10, 5))
                sns.barplot(data=df_ttr, y='author_name', x='msttr', hue='author_name', palette="coolwarm", legend=False, ax=ax)
                plt.title('18. Лексическое Разнообразие (Разнообразие Словарного Запаса)', fontsize=16, fontweight='bold', color="#ffcc00")
                plt.xlabel('Индекс разнообразия слов (выше = богатый язык, ниже = спамер 3 фраз)')
                plt.ylabel('')
                ax.set_xlim(0, df_ttr['msttr'].max() * 1.15)
                for idx, row in df_ttr.iterrows():
                    ax.text(row['msttr'] + (ax.get_xlim()[1] * 0.01), idx, f"{row['msttr']:.3f}",
                            va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
                plt.tight_layout()
                save_chart(images, '18_lexical_diversity.png')
    except Exception as e:
        print(f"Error Chart 18: {e}")

def _generate_chart_19(thirty_days_ago, c, images):
    # 19. Популярность разделов — заменяем pie на hbar
    try:
        c.execute('''
            SELECT board_id, COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY board_id
            ORDER BY cnt DESC
        ''', (thirty_days_ago,))
        board_data = c.fetchall()
        if board_data:
            df_board = pd.DataFrame(board_data, columns=['board_id', 'cnt'])
            total = df_board['cnt'].sum() or 1
            df_board['pct'] = df_board['cnt'] / total * 100

            if len(df_board) > 8:
                top = df_board.head(7).copy()
                others_cnt = df_board.iloc[7:]['cnt'].sum()
                others_pct = df_board.iloc[7:]['pct'].sum()
                top = pd.concat([top,
                    pd.DataFrame([{'board_id': 'other', 'cnt': others_cnt, 'pct': others_pct}])],
                    ignore_index=True)
                df_board = top

            # Sort ascending for hbar (top at top)
            df_board = df_board.sort_values('cnt').reset_index(drop=True)

            cmap_b = plt.get_cmap('RdYlGn')
            max_cnt = df_board['cnt'].max() or 1
            colors_b = [cmap_b(0.15 + 0.75 * v / max_cnt) for v in df_board['cnt']]

            fig, ax = plt.subplots(figsize=(10, 5))
            bars_b = ax.barh(df_board['board_id'], df_board['cnt'],
                             color=colors_b, edgecolor='#0d1117', linewidth=0.6)

            for bar, row in zip(bars_b, df_board.itertuples()):
                ax.text(bar.get_width() + max_cnt * 0.008,
                        bar.get_y() + bar.get_height() / 2,
                        f'{row.cnt:,}  ({row.pct:.1f}%)',
                        va='center', ha='left', fontsize=9, color='#e6edf3', fontweight='bold')

            ax.set_xlim(0, max_cnt * 1.22)
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
            ax.set_xlabel('Постов за 30 дней')
            ax.set_title('19. Популярность разделов (Посты по доскам, 30д)',
                         fontsize=14, fontweight='bold', color='#ffffff')
            # Total annotation
            ax.text(0.99, 0.02, f'Всего: {total:,} постов',
                    transform=ax.transAxes, fontsize=9, color='#8b949e',
                    ha='right', va='bottom', style='italic')
            plt.tight_layout()
            save_chart(images, '19_boards.png')
    except Exception as e:
        print(f"Error Chart 19: {e}")

def _generate_chart_20(thirty_days_ago, c, images):
    # 20. Неравенство богатства битардов (Кривая Лоренца и Индекс Джини)
    # 20. Профиль Чтива (Качество постов по дням)
    try:
        c.execute("SELECT date(timestamp, 'unixepoch', 'localtime') as d, content FROM Posts WHERE timestamp > ?", (thirty_days_ago,))
        posts_data = c.fetchall()

        def clean_text_local2(raw_content):
            if not raw_content:
                return ""
            try:
                content_dict = json.loads(raw_content)
                text = content_dict.get('text', '') or content_dict.get('caption', '') or ''
            except Exception:
                text = raw_content
            if not text:
                return ""
            text_clean = re.sub(r'<[^>]+>', '', text)
            return text_clean

        plot_rows = []
        for r in posts_data:
            d = r['d']
            text = clean_text_local2(r['content'])
            if not text:
                continue

            words = text.split()
            word_count = len(words)
            char_count = len(text)

            if word_count <= 3:
                cat = "Односложные высеры (1-3 слова)"
            elif char_count <= 100:
                cat = "Короткие комменты (<100 симв.)"
            elif char_count <= 400:
                cat = "Обсуждения (100-400 симв.)"
            else:
                cat = "Лонгриды / Пасты (>400 симв.)"

            plot_rows.append({'d': d, 'category': cat})

        if plot_rows:
            df_reading = pd.DataFrame(plot_rows)
            df_counts = df_reading.groupby(['d', 'category']).size().reset_index(name='cnt')
            pivot_df = df_counts.pivot(index='d', columns='category', values='cnt').fillna(0)

            categories_order = [
                "Односложные высеры (1-3 слова)",
                "Короткие комменты (<100 симв.)",
                "Обсуждения (100-400 симв.)",
                "Лонгриды / Пасты (>400 симв.)"
            ]
            pivot_df = pivot_df.reindex(columns=categories_order, fill_value=0)

            row_sums = pivot_df.sum(axis=1)
            pivot_pct = pivot_df.div(row_sums, axis=0).fillna(0) * 100

            fig, ax = plt.subplots(figsize=(10, 6))
            colors = ["#ff3333", "#ff9933", "#3399ff", "#33cc66"]
            pivot_pct.plot.area(ax=ax, color=colors, alpha=0.85)

            plt.title('20. Профиль Чтива (Качество постов по дням)', fontsize=16, fontweight='bold', color="#ffffff")
            plt.xlabel('Дата')
            plt.ylabel('Доля (%)')
            plt.ylim(0, 100)
            plt.legend(loc='lower left', facecolor='#121212', edgecolor='#333333')
            plt.xticks(rotation=45)
            plt.tight_layout()
            save_chart(images, '20_lorenz.png')
    except Exception as e:
        print(f"Error Chart 20: {e}")

def _generate_chart_21(c, images):
    # ── 21. Тепловая карта час × день (180д) ──────────────────────────────
    try:
        import numpy as _np
        from matplotlib.colors import LinearSegmentedColormap
        since_180 = time.time() - 180 * 86400
        c.execute('''
            SELECT cast(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as w,
                   cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                   COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY w, h
        ''', (since_180,))
        data = c.fetchall()
        if data:
            grid = _np.zeros((7, 24))
            for row in data:
                grid[row['w']][row['h']] = row['cnt']

            days_ru_full = ['Воскресенье','Понедельник','Вторник','Среда','Четверг','Пятница','Суббота']
            fig, ax = plt.subplots(figsize=(10, 4.5))
            HEAT = LinearSegmentedColormap.from_list('dv', ['#0d1117','#003d20','#006d35','#39d353','#80ffaa'])
            im = ax.imshow(grid, cmap=HEAT, aspect='auto', interpolation='nearest')

            ax.set_xticks(range(24))
            ax.set_xticklabels([f'{h:02d}:00' for h in range(24)], fontsize=7, rotation=45, ha='right')
            ax.set_yticks(range(7))
            ax.set_yticklabels(days_ru_full, fontsize=8)
            plt.title('21. Тепловая карта час × день недели (180д)', fontsize=15, fontweight='bold', color="#ffffff")
            plt.xlabel('Час суток')

            cb = fig.colorbar(im, ax=ax, pad=0.01)
            cb.ax.yaxis.set_tick_params(color='#ffffff', labelsize=7)
            cb.set_label('постов', color='#ffffff', fontsize=7.5)

            plt.tight_layout()
            save_chart(images, '21_heatmap_180.png')
    except Exception as e:
        print(f"Error Chart 21: {e}")

def _generate_chart_22(c, images):
    # ── 22. Ритм активности по дням недели (90д) ───────────────────────────
    try:
        import numpy as _np
        since_90 = time.time() - 90 * 86400
        c.execute('''
            SELECT cast(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as w,
                   cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                   COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY w, h
        ''', (since_90,))
        data = c.fetchall()
        if data:
            from collections import defaultdict
            dh = defaultdict(lambda: _np.zeros(24))
            for row in data:
                dh[row['w']][row['h']] = row['cnt']

            days_ru = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб']
            day_colors = ['#f78166','#58a6ff','#79c0ff','#d2a8ff','#ffa657','#39d353','#e3b341']
            hrs = _np.arange(24)
            global_max = max((dh[d].max() for d in range(7)), default=1) or 1

            def _smooth(y, w=1):
                k = _np.ones(w*2+1)/(w*2+1)
                return _np.convolve(y, k, mode='same')

            fig, axes = plt.subplots(7, 1, figsize=(12, 7), sharex=True)
            fig.subplots_adjust(hspace=-0.08)
            for idx, d in enumerate(range(6, -1, -1)):
                ax2 = axes[idx]
                ax2.set_facecolor('#121212')
                y = _smooth(dh[d], w=1)
                y_n = y / global_max
                color = day_colors[d]
                ax2.fill_between(hrs, 0, y_n, color=color, alpha=0.42, clip_on=False)
                ax2.plot(hrs, y_n, color=color, linewidth=2, alpha=0.95, clip_on=False)
                ax2.set_xlim(-0.5, 23.5)
                ax2.set_ylim(0, 0.8)
                ax2.text(-0.5, 0.24, days_ru[d], ha='right', va='center',
                        color=color, fontsize=9, fontweight='bold',
                        transform=ax2.get_yaxis_transform())
                total_d = int(dh[d].sum())
                ax2.text(23.4, 0.40, f'{total_d//1000 if total_d>=1000 else total_d}{"k" if total_d>=1000 else ""}',
                        ha='left', va='center', color=color, fontsize=7.5)
                ax2.set_yticks([])
                ax2.spines[:].set_visible(False)
            axes[-1].set_xticks(hrs)
            axes[-1].set_xticklabels([f'{h:02d}' for h in hrs], fontsize=7.5)
            axes[-1].set_xlabel('Час суток')
            fig.suptitle('22. Ритм по дням недели (90д)', fontsize=15, y=0.99, color='#ffffff', fontweight='bold')
            plt.tight_layout(rect=[0.05, 0, 1, 0.98])

            save_chart(images, '22_ridge_weekday.png')
    except Exception as e:
        print(f"Error Chart 22: {e}")

def _generate_chart_23(c, images):
    # ── 23. Часовой циферблат активности (90д) ───────────────────────────
    try:
        import numpy as _np
        since_90 = time.time() - 90 * 86400
        c.execute('''
            SELECT cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                   COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY h ORDER BY h
        ''', (since_90,))
        data = c.fetchall()
        if data:
            hd = {row['h']: row['cnt'] for row in data}
            vals = _np.array([hd.get(h, 0) for h in range(24)], dtype=float)
            vals_norm = vals / (vals.max() or 1)
            total_posts = int(vals.sum())

            fig = plt.figure(figsize=(7, 7))
            ax = fig.add_subplot(111, polar=True)
            ax.set_facecolor('#0a0f14')
            N = 24
            theta = _np.linspace(0, 2*_np.pi, N, endpoint=False) - _np.pi/2
            width = 2*_np.pi / N * 0.82
            cmap = matplotlib.colormaps['RdYlGn']
            ax.bar(theta, vals_norm, width=width, bottom=0.12,
                   color=[cmap(v) for v in vals_norm], alpha=0.92,
                   edgecolor='#121212', linewidth=0.7)
            for i in range(24):
                ax.text(theta[i], 1.26, f'{i:02d}', ha='center', va='center',
                        fontsize=8, color='#ffffff',
                        fontweight='bold' if i in [0,6,12,18] else 'normal')
            peak_hr = int(_np.argmax(vals))
            ax.bar(theta[peak_hr], vals_norm[peak_hr], width=width, bottom=0.12,
                   color='#80ffaa', alpha=0.95, edgecolor='#121212', linewidth=0.7)
            quiet_hr = int(_np.argmin(vals))
            ax.bar(theta[quiet_hr], vals_norm[quiet_hr], width=width, bottom=0.12,
                   color='#f78166', alpha=0.95, edgecolor='#121212', linewidth=0.7)
            ax.set_ylim(0, 1.42)
            ax.set_yticks([])
            ax.set_xticks([])
            ax.spines['polar'].set_visible(False)
            ax.grid(False)
            ax.set_title(f'23. Часовой циферблат активности (90д)\n'
                         f'Пик: {peak_hr:02d}:00  •  Тихо: {quiet_hr:02d}:00  •  {total_posts:,} постов',
                         fontsize=11, pad=14, color='#ffffff', fontweight='bold', y=1.06)
            ax.text(0, 0, f'{total_posts//1000}k', ha='center', va='center',
                    fontsize=14, color='#ffffff', fontweight='bold', alpha=0.55)
            plt.tight_layout()

            save_chart(images, '23_activity_clock.png')
    except Exception as e:
        print(f"Error Chart 23: {e}")

def _generate_chart_24(c, images):
    # ── 24. Календарь активности (180д) ──────────────────────────────────
    try:
        import numpy as _np
        import datetime as _dt
        from matplotlib.colors import LinearSegmentedColormap
        since_180 = time.time() - 180 * 86400
        c.execute('''
            SELECT date(timestamp, 'unixepoch', 'localtime') as day, COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY day ORDER BY day
        ''', (since_180,))
        data = c.fetchall()
        if data:
            day_data = {row['day']: row['cnt'] for row in data}
            dates_sorted = sorted(day_data.keys())
            start = _dt.date.fromisoformat(dates_sorted[0])
            end = _dt.date.fromisoformat(dates_sorted[-1])
            start_mon = start - _dt.timedelta(days=start.weekday())
            end_sun = end + _dt.timedelta(days=6 - end.weekday())
            total_days = (end_sun - start_mon).days + 1
            weeks = total_days // 7
            cal = _np.zeros((7, weeks))
            cur_date = start_mon
            for w in range(weeks):
                for d in range(7):
                    cal[d][w] = day_data.get(cur_date.isoformat(), 0)
                    cur_date += _dt.timedelta(days=1)

            HEAT = LinearSegmentedColormap.from_list('dv', ['#0d1117','#003d20','#006d35','#39d353','#80ffaa'])
            vmax = _np.percentile(list(day_data.values()), 95) if day_data else 1

            fig, ax = plt.subplots(figsize=(max(10, weeks//2), 3))
            im = ax.imshow(cal, cmap=HEAT, aspect='auto', interpolation='nearest', vmin=0, vmax=vmax)

            # Month labels
            month_ticks, month_lbls = [], []
            cdate = start_mon
            seen = set()
            for w in range(weeks):
                ym = cdate.strftime('%b %Y')
                if ym not in seen:
                    month_ticks.append(w)
                    month_lbls.append(cdate.strftime('%b\n%Y'))
                    seen.add(ym)
                cdate += _dt.timedelta(days=7)
            ax.set_xticks(month_ticks)
            ax.set_xticklabels(month_lbls, fontsize=7.5)
            ax.set_yticks(range(7))
            ax.set_yticklabels(['Пн','Вт','Ср','Чт','Пт','Сб','Вс'], fontsize=8)
            plt.title('24. Календарь активности (180д)', fontsize=11, pad=10, color='#ffffff', fontweight='bold')
            cb = fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.18, shrink=0.35)
            cb.set_label('постов/день', color='#ffffff', fontsize=7.5)
            cb.ax.xaxis.set_tick_params(color='#ffffff', labelsize=7)
            plt.tight_layout()

            save_chart(images, '24_calendar_180.png')
    except Exception as e:
        print(f"Error Chart 24: {e}")

def _generate_chart_25(c, images):
    pass

    # ── 25. Кумулятивный рост постов (всё время) ─────────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                c2.execute('''
                    SELECT date(timestamp, 'unixepoch', 'localtime') as d, COUNT(*) as cnt
                    FROM Posts GROUP BY d ORDER BY d
                ''')
                data = c2.fetchall()
                if data:
                    df = pd.DataFrame(data)
                    df['cumsum'] = df['cnt'].cumsum()
                    fig, ax = plt.subplots(figsize=(12, 8))
                    ax.fill_between(range(len(df)), df['cumsum'], alpha=0.25, color='#58a6ff')
                    ax.plot(range(len(df)), df['cumsum'], color='#58a6ff', linewidth=2)
                    step = max(1, len(df) // 8)
                    ax.set_xticks(range(0, len(df), step))
                    ax.set_xticklabels([df['d'].iloc[i] for i in range(0, len(df), step)], rotation=30, fontsize=7.5)
                    ax.set_title('25. Кумулятивный рост постов (всё время)', fontsize=13, fontweight='bold', color='#58a6ff')
                    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
                    plt.tight_layout()
                    save_chart(images, '25_cumulative.png')
    except Exception as e:
        print(f"Error Chart 25: {e}")

def _generate_chart_26(c, images):
    # ── 26. Глубина цепочек ответов (30д) ────────────────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                thirty_d = time.time() - 30 * 86400
                c2.execute('''
                    SELECT p.post_num,
                           COUNT(r.post_num) as reply_count
                    FROM Posts p
                    LEFT JOIN Posts r ON r.reply_to_post_num = p.post_num AND r.board_id = p.board_id
                    WHERE p.timestamp > ?
                    GROUP BY p.post_num
                ''', (thirty_d,))
                data = c2.fetchall()
                if data:
                    counts = [row['reply_count'] for row in data]
                    buckets = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
                    for c in counts:
                        k = min(c, 4)
                        buckets[k] += 1
                    labels = ['0 ответов', '1 ответ', '2 ответа', '3 ответа', '4+']
                    vals   = [buckets[k] for k in range(5)]
                    colors = ['#373b41', '#58a6ff', '#79c0ff', '#d2a8ff', '#ff7b72']
                    fig, ax = plt.subplots(figsize=(7, 4))
                    bars = ax.bar(labels, vals, color=colors, edgecolor='#21262d', linewidth=1.2)
                    for bar, v in zip(bars, vals):
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals)*0.01,
                                f'{v:,}', ha='center', va='bottom', fontsize=8, color='#e6edf3')
                    ax.set_title('26. Глубина цепочек ответов (30д)', fontsize=13, fontweight='bold', color='#d2a8ff')
                    ax.set_ylabel('Количество постов')
                    plt.tight_layout()
                    save_chart(images, '26_reply_depth.png')
    except Exception as e:
        print(f"Error Chart 26: {e}")

def _generate_chart_27(images):
    # ── 27. Радар здоровья борды ──────────────────────────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                t30 = time.time() - 30 * 86400
                t7  = time.time() - 7 * 86400
                c2.execute('SELECT COUNT(*) as n FROM Posts WHERE timestamp > ?', (t30,))
                posts30 = c2.fetchone()['n']
                c2.execute('SELECT COUNT(*) as n FROM Posts WHERE timestamp > ?', (t7,))
                posts7 = c2.fetchone()['n']
                c2.execute('SELECT COUNT(DISTINCT author_id) as n FROM Posts WHERE timestamp > ?', (t30,))
                uniq30 = c2.fetchone()['n']
                c2.execute('SELECT COUNT(*) as n FROM Posts WHERE reply_to_post_num IS NOT NULL AND timestamp > ?', (t30,))
                replies30 = c2.fetchone()['n']
                c2.execute('SELECT AVG(LENGTH(json_extract(content, "$.text"))) as n FROM Posts WHERE timestamp > ?', (t30,))
                avg_len = c2.fetchone()['n'] or 0

                # Normalise each metric against absolute reference baselines
                # 500 posts/30d, 20% unique, 40% reply rate, 150 chars avg = 100%
                categories = ['Активность\n(30д)', 'Темп\n(7д/30д)', 'Уник.\nавторы', 'Диалог\n(%)', 'Длина\nпостов']
                ref_vals = [
                    min(posts30 / 500.0, 1.0),
                    min((posts7 * 4.3) / max(posts30, 1), 1.0),
                    min((uniq30 / max(posts30, 1)) / 0.20, 1.0),
                    min((replies30 / max(posts30, 1)) / 0.40, 1.0),
                    min(avg_len / 150.0, 1.0),
                ]
                N = len(categories)
                angles = [n / float(N) * 2 * 3.14159 for n in range(N)]
                angles += angles[:1]
                vals_r = ref_vals + ref_vals[:1]
                fig = plt.figure(figsize=(7, 7))
                ax = fig.add_subplot(111, polar=True)
                ax.set_facecolor('#0d1117')

                # Fill + border
                ax.fill(angles, vals_r, color='#39d353', alpha=0.22)
                ax.plot(angles, vals_r, color='#39d353', linewidth=2.5)
                # Mark each point with dot + value label
                for angle, val, cat in zip(angles[:-1], ref_vals, categories):
                    ax.plot(angle, val, 'o', color='#39d353', markersize=7, zorder=5)
                    label_r = val + 0.1 if val < 0.85 else val - 0.15
                    clean_cat = cat.replace('\n', ' ')
                    ax.text(angle, label_r, f'{val*100:.0f}%',
                            ha='center', va='center', fontsize=8,
                            color='#80ffaa', fontweight='bold')

                # Gridlines
                ax.set_xticks(angles[:-1])
                ax.set_xticklabels(categories, fontsize=9, color='#e6edf3')
                ax.set_ylim(0, 1)
                ax.set_yticks([0.25, 0.5, 0.75, 1.0])
                ax.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=6.5, color='#484f58')
                ax.grid(color='#21262d', linewidth=0.8, linestyle='--')
                ax.spines['polar'].set_color('#30363d')

                # Overall health score
                score = sum(ref_vals) / len(ref_vals) * 100
                score_color = '#39d353' if score > 66 else '#ffa657' if score > 33 else '#f78166'
                ax.text(0, -0.22, f'Индекс здоровья: {score:.0f}%',
                        transform=ax.transAxes, ha='center', va='center',
                        fontsize=12, color=score_color, fontweight='bold')

                ax.set_title('27. Радар здоровья борды',
                             fontsize=14, fontweight='bold', color='#39d353', pad=22)
                plt.tight_layout()
                save_chart(images, '27_radar.png')
    except Exception as e:
        print(f"Error Chart 27: {e}")

def _generate_chart_28(c, images):
    # ── 28. Топ тредов — пузырьковая диаграмма ───────────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                t90 = time.time() - 90 * 86400
                c2.execute('''
                    SELECT thread_id, COUNT(*) as posts,
                           COUNT(DISTINCT author_id) as authors,
                           MAX(timestamp) as last_ts
                    FROM Posts
                    WHERE timestamp > ? AND thread_id IS NOT NULL AND thread_id != 0
                    GROUP BY thread_id
                    ORDER BY posts DESC LIMIT 20
                ''', (t90,))
                data = c2.fetchall()
                if data and len(data) >= 3:
                    posts   = [row['posts']   for row in data]
                    authors = [row['authors'] for row in data]
                    freshness = [(time.time() - row['last_ts']) / 3600 for row in data]  # hours ago
                    labels  = [f"#{row['thread_id']}" for row in data]
                    sizes   = [max(30, p * 1.5) for p in posts]
                    colors  = [1 - min(f / (7 * 24), 1) for f in freshness]  # freshness → 0..1
                    cmap    = plt.get_cmap('RdYlGn')
                    fig, ax = plt.subplots(figsize=(10, 6))
                    sc = ax.scatter(authors, posts, s=sizes, c=colors, cmap=cmap,
                                    alpha=0.85, edgecolors='#21262d', linewidths=0.8)
                    for i, label in enumerate(labels):
                        ax.annotate(label, (authors[i], posts[i]), fontsize=6.5,
                                    ha='center', va='bottom', color='#e6edf3')
                    plt.colorbar(sc, ax=ax, label='Свежесть (1=только что)')
                    ax.set_xlabel('Уникальных авторов')
                    ax.set_ylabel('Постов в треде')
                    ax.set_title('28. Топ тредов (90д) — размер = активность', fontsize=12,
                                 fontweight='bold', color='#ffa657')
                    plt.tight_layout()
                    save_chart(images, '28_threads_bubble.png')
    except Exception as e:
        print(f"Error Chart 28: {e}")

def _generate_chart_29(images):
    # ── 29. Тренд медиа vs текст по дням (30д) ─────────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                t30_29 = time.time() - 30 * 86400
                c2.execute('''
                    SELECT date(timestamp, 'unixepoch', 'localtime') as d,
                           SUM(CASE WHEN content LIKE '%"type": "text"%' THEN 1 ELSE 0 END) as txt,
                           SUM(CASE WHEN content LIKE '%"type": "photo"%' OR content LIKE '%"type": "video"%' OR content LIKE '%"type": "animation"%' OR content LIKE '%"type": "sticker"%' THEN 1 ELSE 0 END) as med
                    FROM Posts WHERE timestamp > ? GROUP BY d ORDER BY d
                ''', (t30_29,))
                rows29 = c2.fetchall()
                if rows29:
                    df29 = pd.DataFrame(rows29)
                    xs29 = list(range(len(df29)))
                    fig, ax = plt.subplots(figsize=(11, 4))
                    ax.stackplot(xs29, df29['txt'], df29['med'],
                                 labels=['Текст', 'Медиа'],
                                 colors=['#58a6ff', '#ff3399'], alpha=0.82)
                    step29 = max(1, len(df29) // 10)
                    ax.set_xticks(xs29[::step29])
                    ax.set_xticklabels(df29['d'].tolist()[::step29], rotation=30, ha='right', fontsize=7.5)
                    ax.set_ylabel('Постов в день')
                    ax.legend(loc='upper left', fontsize=9)
                    ax.set_title('29. Тренд медиа vs текст по дням (30д)', fontsize=13,
                                 fontweight='bold', color='#ff3399')
                    plt.tight_layout()
                    save_chart(images, '29_media_trend.png')
    except Exception as e:
        print(f"Error Chart 29: {e}")

def _generate_chart_30(images):
    # ── 30. Когорты новых авторов по неделям (13 нед) ─────────────────────────
    try:
        with contextlib.closing(connect_stats_db()) as conn2:
            conn2.row_factory = dict_factory
            with contextlib.closing(conn2.cursor()) as c2:
                t91 = time.time() - 91 * 86400
                c2.execute('''
                    SELECT author_id,
                           strftime('%Y-%W', datetime(MIN(timestamp), 'unixepoch', 'localtime')) as first_week,
                           COUNT(*) as posts
                    FROM Posts
                    WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
                    GROUP BY author_id
                ''', (t91,))
                data = c2.fetchall()
                if data:
                    from collections import defaultdict
                    cohort = defaultdict(lambda: {'new': 0, 'posts': 0})
                    for row in data:
                        wk = row['first_week']
                        cohort[wk]['new']   += 1
                        cohort[wk]['posts'] += row['posts']
                    weeks_sorted = sorted(cohort.keys())[-13:]
                    new_users = [cohort[w]['new']   for w in weeks_sorted]
                    avg_posts = [cohort[w]['posts'] / max(cohort[w]['new'], 1) for w in weeks_sorted]
                    x = range(len(weeks_sorted))
                    fig, ax1 = plt.subplots(figsize=(11, 4))
                    ax2 = ax1.twinx()
                    ax1.bar(x, new_users, color='#58a6ff', alpha=0.75, label='Новых авторов')
                    ax2.plot(x, avg_posts, color='#ffa657', linewidth=2, marker='o', label='Ср. постов')
                    ax1.set_xticks(list(x))
                    ax1.set_xticklabels([w.replace('20', '') for w in weeks_sorted], rotation=30, fontsize=7.5)
                    ax1.set_ylabel('Новых авторов', color='#58a6ff')
                    ax2.set_ylabel('Ср. постов на автора', color='#ffa657')
                    ax1.set_title('30. Когорты новых авторов (13 нед)', fontsize=13,
                                  fontweight='bold', color='#58a6ff')
                    lines1, labels1 = ax1.get_legend_handles_labels()
                    lines2, labels2 = ax2.get_legend_handles_labels()
                    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper left')
                    plt.tight_layout()
                    save_chart(images, '30_cohorts.png')
    except Exception as e:
        print(f"Error Chart 30: {e}")

def _generate_chart_31(images):
    # ── 31. Активность борд по неделям (12 нед) stacked area ─────────────────
    try:
        with contextlib.closing(connect_stats_db()) as _conn31:
            _conn31.row_factory = dict_factory
            with contextlib.closing(_conn31.cursor()) as _c31:
                _t84 = time.time() - 84 * 86400
                _c31.execute('''
                    SELECT strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as wk,
                           board_id, COUNT(*) as cnt
                    FROM Posts WHERE timestamp > ? AND board_id IS NOT NULL
                    GROUP BY wk, board_id ORDER BY wk
                ''', (_t84,))
                _rows31 = _c31.fetchall()
                if _rows31:
                    _df31 = pd.DataFrame(_rows31)
                    _bt31 = _df31.groupby('board_id')['cnt'].sum().sort_values(ascending=False)
                    _top_b31 = _bt31.index[:7].tolist()
                    _df31['board_id'] = _df31['board_id'].apply(lambda b: b if b in _top_b31 else 'other')
                    _df31 = _df31.groupby(['wk', 'board_id'], as_index=False)['cnt'].sum()
                    _piv31 = _df31.pivot(index='wk', columns='board_id', values='cnt').fillna(0)
                    _piv31 = _piv31.reindex(sorted(_piv31.index))
                    _bords31 = list(_piv31.columns)
                    _xs31 = list(range(len(_piv31)))
                    _cl31 = list(plt.cm.Set2.colors[:len(_bords31)])
                    fig, ax = plt.subplots(figsize=(13, 5))
                    ax.stackplot(_xs31, [_piv31[b].values for b in _bords31],
                                 labels=_bords31, colors=_cl31[:len(_bords31)], alpha=0.85)
                    _step31 = max(1, len(_piv31) // 10)
                    ax.set_xticks(_xs31[::_step31])
                    ax.set_xticklabels(_piv31.index.tolist()[::_step31], rotation=30, ha='right', fontsize=8)
                    ax.set_ylabel('Постов в неделю')
                    ax.legend(loc='upper left', fontsize=9, framealpha=0.7)
                    ax.set_title('31. Активность борд по неделям (12 нед)',
                                 fontsize=13, fontweight='bold', color='#ffa657')
                    plt.tight_layout()
                    save_chart(images, '31_boards_weekly.png')
    except Exception as e:
        print(f"Error Chart 31: {e}")

def _generate_chart_32(images):
    # ── 32. Стрик-чемпионы (60д) Top-20, dual-column ─────────────────────────
    try:
        import datetime as _dt32
        from collections import defaultdict as _dd32
        with contextlib.closing(connect_stats_db()) as _conn32:
            _conn32.row_factory = dict_factory
            with contextlib.closing(_conn32.cursor()) as _c32:
                _t60 = time.time() - 60 * 86400
                _c32.execute('''
                    SELECT author_id, date(timestamp, 'unixepoch', 'localtime') as d
                    FROM Posts
                    WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
                    GROUP BY author_id, d ORDER BY author_id, d
                ''', (_t60,))
                _rows32 = _c32.fetchall()
                if _rows32:
                    _ud32 = _dd32(list)
                    for _r32 in _rows32:
                        _ud32[_r32['author_id']].append(_r32['d'])
                    _streaks32 = []
                    for _uid32, _days32 in _ud32.items():
                        _ds32 = sorted(set(_days32)); _mx32 = 1; _cur32 = 1
                        for _i32 in range(1, len(_ds32)):
                            _d0_32 = _dt32.date.fromisoformat(_ds32[_i32-1])
                            _d1_32 = _dt32.date.fromisoformat(_ds32[_i32])
                            if (_d1_32 - _d0_32).days == 1:
                                _cur32 += 1; _mx32 = max(_mx32, _cur32)
                            else:
                                _cur32 = 1
                        _streaks32.append({'author_id': _uid32, 'streak': _mx32, 'days': len(_ds32)})
                    _streaks32 = sorted(_streaks32, key=lambda x: x['streak'], reverse=True)[:20]
                    _df32 = pd.DataFrame(_streaks32)
                    _df32['author_name'] = _df32['author_id'].apply(generate_schizo_name)
                    _half32 = len(_df32) // 2
                    _df32l = _df32.iloc[:_half32].reset_index(drop=True)
                    _df32r = _df32.iloc[_half32:].reset_index(drop=True)
                    _mx_s32 = _df32['streak'].max() or 1
                    fig, (_ax32l, _ax32r) = plt.subplots(1, 2, figsize=(18, 7))
                    for _ax32, _d32, _t32 in [(_ax32l, _df32l.iloc[::-1].reset_index(drop=True), 'Топ 1–10'),
                                                (_ax32r, _df32r.iloc[::-1].reset_index(drop=True), 'Топ 11–20')]:
                        _colors32 = [plt.cm.RdYlGn(v / _mx_s32) for v in _d32['streak']]
                        _bars32 = _ax32.barh(_d32['author_name'], _d32['streak'],
                                             color=_colors32, edgecolor='#1c2128', linewidth=0.7)
                        for _bar32, _row32 in zip(_bars32, _d32.itertuples()):
                            _ax32.text(_bar32.get_width() + _mx_s32 * 0.01,
                                       _bar32.get_y() + _bar32.get_height() / 2,
                                       f'{_row32.streak}д  ({_row32.days} активных)',
                                       va='center', ha='left', fontsize=8, color='#e6edf3')
                        _ax32.set_xlim(0, _mx_s32 * 1.35)
                        _ax32.set_xlabel('Серия (дней подряд)')
                        _ax32.set_ylabel('')
                        _ax32.set_title(_t32, fontsize=12, color='#39d353')
                    plt.suptitle('32. Стрик-чемпионы (60д) — самые стойкие аноны  Top-20',
                                 fontsize=14, fontweight='bold', color='#39d353', y=1.01)
                    plt.tight_layout()
                    save_chart(images, '32_streak_champions.png', bbox_inches='tight')
    except Exception as e:
        print(f"Error Chart 32: {e}")


def _generate_chart_33(c, images):
    # ── 33. Velocity Map: Скорость Деградации ────────────────────────────────
    try:
        import numpy as _np
        t30 = time.time() - 30 * 86400
        c.execute('''
            SELECT
                date(timestamp, 'unixepoch', 'localtime') as d,
                cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY d, h ORDER BY d, h
        ''', (t30,))
        rows = c.fetchall()
        if rows:
            from collections import defaultdict
            day_hours = defaultdict(lambda: _np.zeros(24))
            for r in rows:
                day_hours[r['d']][r['h']] = r['cnt']
            days_sorted = sorted(day_hours.keys())
            daily_peak = [day_hours[d].max() for d in days_sorted]
            daily_total = [int(day_hours[d].sum()) for d in days_sorted]

            df_v = pd.DataFrame({'d': days_sorted, 'peak': daily_peak, 'total': daily_total})
            roll7 = pd.Series(daily_total).rolling(7, min_periods=1).mean().tolist()

            xs = list(range(len(df_v)))
            fig, ax1 = plt.subplots(figsize=(13, 5))
            ax2 = ax1.twinx()

            ax1.bar(xs, df_v['total'], color='#334455', alpha=0.6, label='Постов/день')
            ax1.plot(xs, roll7, color='#58a6ff', linewidth=2.5, label='Скользящее ср. 7д', zorder=3)

            ax2.plot(xs, df_v['peak'], color='#ff3366', linewidth=1.5, linestyle='--', alpha=0.85, label='Пиковый час')

            # Annotate top 3 velocity spikes
            peaks_idx = sorted(range(len(daily_total)), key=lambda i: daily_total[i], reverse=True)[:3]
            for pi in peaks_idx:
                ax1.annotate(f"{daily_total[pi]}",
                             xy=(pi, daily_total[pi]), xytext=(pi, daily_total[pi] * 1.05),
                             fontsize=7.5, color='#80ffaa', ha='center', fontweight='bold')

            step = max(1, len(df_v) // 10)
            ax1.set_xticks(xs[::step])
            ax1.set_xticklabels(df_v['d'].tolist()[::step], rotation=30, ha='right', fontsize=7.5)
            ax1.set_ylabel('Постов в день', color='#58a6ff')
            ax2.set_ylabel('Пиковых постов/час', color='#ff3366')
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))

            lines1, lbs1 = ax1.get_legend_handles_labels()
            lines2, lbs2 = ax2.get_legend_handles_labels()
            ax1.legend(lines1 + lines2, lbs1 + lbs2, fontsize=8, loc='upper left')
            ax1.set_title('33. Velocity Map — Скорость деградации борды (30д)',
                          fontsize=13, fontweight='bold', color='#58a6ff')
            plt.tight_layout()
            save_chart(images, '33_velocity.png')
    except Exception as e:
        print(f"Error Chart 33: {e}")


def _generate_chart_34(c, images):
    # ── 34. Churned Users — Кто Слился ────────────────────────────────────────
    try:
        now = time.time()
        t7  = now - 7  * 86400
        t14 = now - 14 * 86400
        # Users active 8-14 days ago
        c.execute('''
            SELECT author_id, COUNT(*) as old_posts
            FROM Posts
            WHERE timestamp BETWEEN ? AND ? AND author_id IS NOT NULL AND author_id != 0
            GROUP BY author_id
        ''', (t14, t7))
        old_active = {r['author_id']: r['old_posts'] for r in c.fetchall()}

        # Users active last 7 days
        c.execute('''
            SELECT DISTINCT author_id FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
        ''', (t7,))
        recent_active = {r['author_id'] for r in c.fetchall()}

        churned = [(uid, cnt) for uid, cnt in old_active.items() if uid not in recent_active]
        churned = sorted(churned, key=lambda x: x[1], reverse=True)[:15]

        if churned:
            df_ch = pd.DataFrame(churned, columns=['author_id', 'posts'])
            df_ch['name'] = df_ch['author_id'].apply(generate_schizo_name)
            df_ch = df_ch.iloc[::-1].reset_index(drop=True)  # reverse for hbar

            fig, ax = plt.subplots(figsize=(10, 6))
            cmap_ch = plt.get_cmap('Reds')
            max_p = df_ch['posts'].max() or 1
            colors_ch = [cmap_ch(0.4 + 0.55 * v / max_p) for v in df_ch['posts']]
            bars_ch = ax.barh(df_ch['name'], df_ch['posts'], color=colors_ch,
                              edgecolor='#1c2128', linewidth=0.7)
            for bar, val in zip(bars_ch, df_ch['posts']):
                ax.text(bar.get_width() + max_p * 0.01,
                        bar.get_y() + bar.get_height() / 2,
                        f'{val}п', va='center', ha='left', fontsize=8.5, color='#e6edf3')
            ax.set_xlim(0, max_p * 1.25)
            ax.set_xlabel('Постов за предыдущую неделю')
            ax.set_title('34. Churned Users — Кто слился за последнюю неделю (топ-15)',
                         fontsize=12, fontweight='bold', color='#f78166')
            plt.tight_layout()
            save_chart(images, '34_churned.png')
    except Exception as e:
        print(f"Error Chart 34: {e}")


def _generate_chart_35(c, images):
    # ── 35. Bump Chart — Недельный рейтинг топ-5 авторов (8 нед) ─────────────
    try:
        import numpy as _np
        t56 = time.time() - 56 * 86400
        c.execute('''
            SELECT
                strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as wk,
                author_id,
                COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
            GROUP BY wk, author_id
        ''', (t56,))
        rows = c.fetchall()
        if not rows:
            return

        df_b = pd.DataFrame(rows)
        weeks = sorted(df_b['wk'].unique())
        if len(weeks) < 3:
            return

        # Find top-5 authors by total posts
        top5 = df_b.groupby('author_id')['cnt'].sum().sort_values(ascending=False).head(5).index.tolist()

        # Build rank table: week × author → rank (1=top)
        rank_data = {uid: [] for uid in top5}
        for wk in weeks:
            wk_df = df_b[df_b['wk'] == wk].sort_values('cnt', ascending=False).reset_index(drop=True)
            wk_ranks = {row['author_id']: idx + 1 for idx, row in wk_df.iterrows()}
            for uid in top5:
                rank_data[uid].append(wk_ranks.get(uid, len(wk_df) + 1))

        fig, ax = plt.subplots(figsize=(12, 6))
        colors_bump = ['#58a6ff', '#ffa657', '#39d353', '#f78166', '#d2a8ff']
        x_positions = list(range(len(weeks)))

        for idx, uid in enumerate(top5):
            ranks = rank_data[uid]
            color = colors_bump[idx % len(colors_bump)]
            name_short = generate_schizo_name(uid)
            ax.plot(x_positions, ranks, marker='o', linewidth=2.5, markersize=8,
                    color=color, label=name_short, zorder=3)
            # Rank labels
            for xi, rk in zip(x_positions, ranks):
                ax.text(xi, rk - 0.18, f'#{rk}', ha='center', va='bottom',
                        fontsize=7.5, color=color, fontweight='bold')

        ax.set_xticks(x_positions)
        ax.set_xticklabels([w.replace('20', '') for w in weeks], rotation=30, ha='right', fontsize=8)
        ax.invert_yaxis()
        ax.set_ylabel('Место в рейтинге')
        max_rank = max(max(ranks) for ranks in rank_data.values()) if rank_data else 10
        ax.set_ylim(max(max_rank + 1, 8), 0.5)   # always show at least 8 positions
        ax.set_yticks(range(1, max(max_rank + 1, 8)))
        ax.legend(fontsize=7.5, loc='lower right', framealpha=0.7)
        ax.set_title('35. Bump Chart — Недельный рейтинг топ-5 авторов (8 нед)',
                     fontsize=13, fontweight='bold', color='#d2a8ff')
        ax.grid(axis='x', alpha=0.3)
        plt.tight_layout()
        save_chart(images, '35_bump_chart.png')
    except Exception as e:
        print(f"Error Chart 35: {e}")


def _generate_chart_36(c, images):
    # ── 36. Хронотип — Scatter авторов по среднему часу активности ───────────
    try:
        t30 = time.time() - 30 * 86400
        c.execute('''
            SELECT author_id,
                   AVG(cast(strftime('%H', datetime(timestamp,'unixepoch','localtime')) as real)) as mean_hour,
                   COUNT(*) as posts
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
            GROUP BY author_id
            HAVING COUNT(*) >= 5
        ''', (t30,))
        rows = c.fetchall()
        if not rows:
            return

        df_chr = pd.DataFrame(rows)

        def chronotype(h):
            if h < 6:  return 'Ночник (00-06)', '#6600cc'
            elif h < 12: return 'Утренник (06-12)', '#ffcc00'
            elif h < 18: return 'Дневник (12-18)', '#00ccff'
            else: return 'Вечерник (18-24)', '#ff6600'

        df_chr['label'], df_chr['color'] = zip(*df_chr['mean_hour'].apply(chronotype))

        fig, ax = plt.subplots(figsize=(11, 7))
        for lbl, grp in df_chr.groupby('label'):
            ax.scatter(grp['mean_hour'], grp['posts'],
                       c=grp['color'], s=grp['posts'].clip(upper=500) * 0.8 + 20,
                       alpha=0.75, edgecolors='#0d1117', linewidths=0.5, label=lbl)

        # Annotate top-3 per chronotype
        for lbl, grp in df_chr.groupby('label'):
            top3 = grp.nlargest(3, 'posts')
            for _, row in top3.iterrows():
                short = generate_schizo_name(int(row['author_id'])).split(' ')[0]
                ax.annotate(short, (row['mean_hour'], row['posts']),
                            fontsize=6.5, color=row['color'], alpha=0.9,
                            xytext=(3, 3), textcoords='offset points')

        ax.set_xlabel('Средний час активности (МСК)')
        ax.set_ylabel('Постов за 30 дней')
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 24, 2)], fontsize=8)
        ax.axvline(6,  color='#ffcc00', linestyle='--', alpha=0.4, linewidth=1)
        ax.axvline(12, color='#00ccff', linestyle='--', alpha=0.4, linewidth=1)
        ax.axvline(18, color='#ff6600', linestyle='--', alpha=0.4, linewidth=1)
        ax.legend(fontsize=9, framealpha=0.7)
        ax.set_title('36. Хронотип — Когда сидит каждый анон (30д)',
                     fontsize=13, fontweight='bold', color='#ffcc00')

        # Board chronotype summary annotation
        board_mean = df_chr['mean_hour'].mean()
        chtype_board = chronotype(board_mean)[0]
        ax.text(0.99, 0.98, f'Борда в целом: {chtype_board}',
                transform=ax.transAxes, fontsize=9, color='#ffffff',
                ha='right', va='top', style='italic',
                bbox=dict(facecolor='#21262d', edgecolor='#30363d', boxstyle='round,pad=0.4'))

        plt.tight_layout()
        save_chart(images, '36_chronotype.png')
    except Exception as e:
        print(f"Error Chart 36: {e}")


def _generate_chart_37(c, images):
    # ── 37. Матрица Хайпа — 7×24 со стрелками тренда ────────────────────────
    try:
        import numpy as _np
        now = time.time()
        t28  = now - 28 * 86400
        t14  = now - 14 * 86400

        def _fetch_grid(since, until=None):
            if until:
                c.execute('''
                    SELECT cast(strftime('%w', datetime(timestamp,'unixepoch','localtime')) as integer) as w,
                           cast(strftime('%H', datetime(timestamp,'unixepoch','localtime')) as integer) as h,
                           COUNT(*) as cnt
                    FROM Posts WHERE timestamp BETWEEN ? AND ?
                    GROUP BY w, h
                ''', (since, until))
            else:
                c.execute('''
                    SELECT cast(strftime('%w', datetime(timestamp,'unixepoch','localtime')) as integer) as w,
                           cast(strftime('%H', datetime(timestamp,'unixepoch','localtime')) as integer) as h,
                           COUNT(*) as cnt
                    FROM Posts WHERE timestamp > ?
                    GROUP BY w, h
                ''', (since,))
            g = _np.zeros((7, 24))
            for r in c.fetchall():
                g[r['w']][r['h']] = r['cnt']
            return g

        grid_cur  = _fetch_grid(t14)        # last 14 days
        grid_prev = _fetch_grid(t28, t14)   # 14 days before that

        # Trend: +1 up, -1 down, 0 flat
        delta = grid_cur - grid_prev
        trend = _np.sign(delta).astype(int)

        # Normalize current for coloring
        vmax = _np.percentile(grid_cur[grid_cur > 0], 95) if grid_cur.max() > 0 else 1
        grid_norm = _np.clip(grid_cur / (vmax or 1), 0, 1)

        days_ru_s = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб']
        fig, ax = plt.subplots(figsize=(16, 5))
        ax.set_facecolor('#0d1117')

        from matplotlib.colors import LinearSegmentedColormap
        CMAP = LinearSegmentedColormap.from_list('hype', ['#0d1117','#003d20','#39d353','#80ffaa'])

        for d in range(7):
            for h in range(24):
                val = grid_norm[d][h]
                color = CMAP(val)
                rect = plt.Rectangle([h - 0.45, d - 0.45], 0.9, 0.9,
                                     facecolor=color, edgecolor='#21262d', linewidth=0.4)
                ax.add_patch(rect)
                # Trend arrow
                tr = trend[d][h]
                if tr == 1:
                    ax.text(h, d + 0.32, '▲', ha='center', va='center',
                            fontsize=5.5, color='#39d353', alpha=0.9)
                elif tr == -1:
                    ax.text(h, d + 0.32, '▼', ha='center', va='center',
                            fontsize=5.5, color='#f78166', alpha=0.9)
                # Post count (small)
                cnt_val = int(grid_cur[d][h])
                if cnt_val > 0:
                    ax.text(h, d - 0.08, str(cnt_val), ha='center', va='center',
                            fontsize=4.5, color='#e6edf3', alpha=0.75)

        ax.set_xlim(-0.5, 23.5)
        ax.set_ylim(-0.5, 6.5)
        ax.set_xticks(range(24))
        ax.set_xticklabels([f'{h:02d}' for h in range(24)], fontsize=7.5)
        ax.set_yticks(range(7))
        ax.set_yticklabels(days_ru_s, fontsize=9)
        ax.set_xlabel('Час суток')
        ax.set_title('37. Матрица Хайпа — активность 7×24 со стрелками тренда (▲▼ vs прошлые 2 нед)',
                     fontsize=12, fontweight='bold', color='#80ffaa')
        plt.tight_layout()
        save_chart(images, '37_hype_matrix.png')
    except Exception as e:
        print(f"Error Chart 37: {e}")


def _generate_chart_38(c, images):
    # ── 38. Эмодзи-Борда — Топ-20 эмодзи из постов ───────────────────────────
    try:
        import re as _re
        t30 = time.time() - 30 * 86400
        c.execute('''
            SELECT content FROM Posts
            WHERE timestamp > ? AND content IS NOT NULL
        ''', (t30,))
        rows = c.fetchall()
        if not rows:
            return

        # Unicode emoji regex (broad coverage)
        EMOJI_RE = _re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # misc symbols
            "\U0001F680-\U0001F6FF"  # transport
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001f926-\U0001f937"
            "\U00010000-\U0010ffff"
            "\u2640-\u2642"
            "\u2600-\u2B55"
            "\u200d"
            "\u23cf"
            "\u23e9"
            "\u231a"
            "\ufe0f"
            "\u3030"
            "]+", flags=_re.UNICODE)

        from collections import Counter
        emoji_counter = Counter()
        for r in rows:
            raw = r['content'] or ''
            # Extract text from JSON
            try:
                d = json.loads(raw)
                text = d.get('text', '') or d.get('caption', '') or ''
            except Exception:
                text = raw
            found = EMOJI_RE.findall(text)
            for em_group in found:
                # Split compound emoji to individual graphemes where possible
                for char in em_group:
                    if EMOJI_RE.match(char):
                        emoji_counter[char] += 1

        top_emoji = emoji_counter.most_common(20)
        if not top_emoji:
            return

        emojis  = [e for e, _ in top_emoji]
        counts  = [c for _, c in top_emoji]
        max_cnt = max(counts) or 1

        # Color gradient by count
        cmap_em = plt.get_cmap('YlOrRd')
        colors_em = [cmap_em(0.3 + 0.65 * v / max_cnt) for v in counts]

        fig, ax = plt.subplots(figsize=(10, 7))
        bars_em = ax.barh(range(len(emojis)), counts, color=colors_em,
                          edgecolor='#21262d', linewidth=0.6)
        ax.set_yticks(range(len(emojis)))
        # Direct path lookup for Windows emoji font (findfont fails for color fonts)
        import matplotlib.font_manager as _fm
        import os as _os
        emoji_font_prop = None
        _win_emoji_paths = [
            r'C:\Windows\Fonts\seguiemj.ttf',   # Segoe UI Emoji
            r'C:\Windows\Fonts\seguisym.ttf',   # Segoe UI Symbol fallback
        ]
        for _fp in _win_emoji_paths:
            if _os.path.exists(_fp):
                try:
                    emoji_font_prop = _fm.FontProperties(fname=_fp)
                    break
                except Exception:
                    pass
        try:
            if emoji_font_prop:
                ax.set_yticklabels(emojis, fontsize=13, fontproperties=emoji_font_prop)
            else:
                # No emoji font found — show Unicode codepoints
                hex_labels = ['+'.join(f'U+{ord(c):04X}' for c in e if ord(c) > 127) or e for e in emojis]
                ax.set_yticklabels(hex_labels, fontsize=8.5)
        except Exception:
            ax.set_yticklabels([str(i+1) for i in range(len(emojis))], fontsize=9)

        for bar, val in zip(bars_em, counts):
            ax.text(bar.get_width() + max_cnt * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f'{val:,}', va='center', fontsize=9, color='#e6edf3', fontweight='bold')

        ax.set_xlim(0, max_cnt * 1.2)
        ax.set_xlabel('Упоминаний за 30 дней')
        ax.invert_yaxis()
        ax.set_title('38. Эмодзи-Борда — Топ-20 эмодзи (30д)',
                     fontsize=13, fontweight='bold', color='#ffa657')
        plt.tight_layout()
        save_chart(images, '38_emoji_board.png')
    except Exception as e:
        print(f"Error Chart 38: {e}")


def _generate_chart_39(c, images):
    # ── 39. Сеть Тредов — граф тредов соединённых общими авторами ────────────
    try:
        import networkx as _nx
        t30 = time.time() - 30 * 86400
        c.execute('''
            SELECT author_id, thread_id, COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND thread_id IS NOT NULL
              AND author_id != 0 AND thread_id != 0
            GROUP BY author_id, thread_id
        ''', (t30,))
        rows = c.fetchall()
        if not rows:
            return

        from collections import defaultdict
        author_threads = defaultdict(set)
        thread_posts = defaultdict(int)
        for r in rows:
            author_threads[r['author_id']].add(r['thread_id'])
            thread_posts[r['thread_id']] += r['cnt']

        # Top-40 threads by posts
        top_threads = set(sorted(thread_posts, key=thread_posts.get, reverse=True)[:40])

        G_t = _nx.Graph()
        for uid, threads in author_threads.items():
            threads_top = [t for t in threads if t in top_threads]
            for i, t1 in enumerate(threads_top):
                for t2 in threads_top[i+1:]:
                    if G_t.has_edge(t1, t2):
                        G_t[t1][t2]['weight'] += 1
                    else:
                        G_t.add_edge(t1, t2, weight=1)

        if len(G_t) < 3:
            return

        # Remove only truly weak edges (keep weight >= 1 — any shared author is a connection)
        weak = [(u, v) for u, v, d in G_t.edges(data=True) if d['weight'] < 1]
        G_t.remove_edges_from(weak)
        if len(G_t) < 3:
            return

        # Node size = posts, color = degree
        node_sizes = [max(30, thread_posts.get(n, 1) * 0.3) for n in G_t.nodes()]
        degrees = dict(G_t.degree())
        node_colors = [degrees[n] for n in G_t.nodes()]
        edge_weights = [d['weight'] for _, _, d in G_t.edges(data=True)]
        max_ew = max(edge_weights) if edge_weights else 1
        edge_widths = [0.5 + 2.5 * (w / max_ew) for w in edge_weights]

        fig, ax = plt.subplots(figsize=(11, 9))
        ax.set_facecolor('#0d1117')
        pos = _nx.spring_layout(G_t, k=0.4, seed=42)
        _nx.draw_networkx_nodes(G_t, pos, node_size=node_sizes,
                                node_color=node_colors, cmap=plt.cm.plasma, ax=ax, alpha=0.9)
        _nx.draw_networkx_edges(G_t, pos, width=edge_widths, alpha=0.35,
                                edge_color='#58a6ff', ax=ax)
        # Label top-10 nodes by post count
        top10_nodes = sorted(G_t.nodes(), key=lambda n: thread_posts.get(n, 0), reverse=True)[:10]
        labels = {n: f'#{n}' for n in top10_nodes}
        _nx.draw_networkx_labels(G_t, pos, labels, font_size=7, font_color='#e6edf3', ax=ax)

        ax.axis('off')
        ax.set_title('39. Сеть тредов — связи через общих авторов (30д)\n'
                     'Размер = постов, ширина ребра = общих авторов, цвет = связность',
                     fontsize=12, fontweight='bold', color='#58a6ff', pad=12)
        plt.tight_layout()
        save_chart(images, '39_thread_network.png')
    except Exception as e:
        print(f"Error Chart 39: {e}")


def _generate_chart_40(images):
    # ── 40. AI Weekly Digest — нарратив от Groq ──────────────────────────────
    try:
        import os as _os
        import requests as _req
        from dotenv import load_dotenv as _ld
        _ld(_os.path.join(_os.path.dirname(__file__), '.env'))

        # --- Gather key metrics from DB ---
        with contextlib.closing(connect_stats_db()) as _conn:
            _conn.row_factory = dict_factory
            with contextlib.closing(_conn.cursor()) as _c:
                t7  = time.time() - 7 * 86400
                t30 = time.time() - 30 * 86400

                _c.execute('SELECT COUNT(*) as n FROM Posts WHERE timestamp > ?', (t7,))
                posts_7d = _c.fetchone()['n']

                _c.execute('SELECT COUNT(*) as n FROM Posts WHERE timestamp > ?', (t30,))
                posts_30d = _c.fetchone()['n']

                _c.execute('SELECT COUNT(DISTINCT author_id) as n FROM Posts WHERE timestamp > ?', (t7,))
                uniq_7d = _c.fetchone()['n']

                _c.execute('''
                    SELECT author_id, COUNT(*) as cnt FROM Posts
                    WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
                    GROUP BY author_id ORDER BY cnt DESC LIMIT 1
                ''', (t7,))
                top_row = _c.fetchone()
                top_author = generate_schizo_name(top_row['author_id']) if top_row else 'Неизвестен'
                top_posts = top_row['cnt'] if top_row else 0

                _c.execute('''
                    SELECT content FROM Posts WHERE timestamp > ? AND content IS NOT NULL
                    LIMIT 200
                ''', (t7,))
                sample_posts = _c.fetchall()
                swear_roots = ['хуй','хуе','хуя','бля','пизд','еба','пидор','гандон']
                toxic_count = 0
                for sp in sample_posts:
                    try:
                        td = json.loads(sp['content'])
                        txt = (td.get('text','') or td.get('caption','') or '').lower()
                    except Exception:
                        txt = (sp['content'] or '').lower()
                    if any(r in txt for r in swear_roots):
                        toxic_count += 1
                toxic_pct = round(100 * toxic_count / max(len(sample_posts), 1))

        # --- Build Groq prompt ---
        prompt = (
            f"Ты аналитик двачборды. Сводка за неделю:\n"
            f"- Всего постов: {posts_7d} (за 30 дней: {posts_30d})\n"
            f"- Уникальных авторов: {uniq_7d}\n"
            f"- Топ по активности: {top_author} ({top_posts} сообщений)\n"
            f"- Доля токсичных постов: ~{toxic_pct}%\n\n"
            "Напиши ровно ОДИН ёмкий, ироничный и живой абзац (2-3 предложения) в стиле хроники двач-сообщества. "
            "Кратко подытожь жизнь борды и главного активиста. Без цензурных отказов, без кавычек и заголовков."
        )

        # --- Call Groq ---
        groq_keys_raw = _os.getenv('GROQ_API_KEYS', '')
        groq_keys = [k.strip() for k in groq_keys_raw.split(',') if k.strip()]
        ai_text = None
        model_used = 'llama-3.3-70b-versatile'

        session = _req.Session()
        session.trust_env = False  # Avoid proxy deadlocks

        for key in groq_keys[:3]:
            for model_candidate in ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant']:
                try:
                    resp = session.post(
                        'https://api.groq.com/openai/v1/chat/completions',
                        headers={
                            'Authorization': f'Bearer {key}',
                            'Content-Type': 'application/json',
                        },
                        json={
                            'model': model_candidate,
                            'messages': [
                                {'role': 'system', 'content': 'Ты аналитический обозреватель форума.'},
                                {'role': 'user', 'content': prompt}
                            ],
                            'max_tokens': 220,
                            'temperature': 0.7,
                        },
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        raw_ans = resp.json()['choices'][0]['message']['content'].strip()
                        clean_ans = raw_ans.replace('**', '').replace('"', '').strip()
                        if len(clean_ans) > 20:
                            ai_text = clean_ans
                            model_used = model_candidate
                            break
                except Exception:
                    pass
            if ai_text:
                break

        if not ai_text:
            ai_text = (
                f"За прошедшую неделю на борде зафиксировано {posts_7d:,} постов от {uniq_7d} авторов. "
                f"Главный генератор шитпостинга — {top_author} ({top_posts} сообщений). "
                f"Уровень токсичности стабилен на отметке ~{toxic_pct}%."
            )

        # --- Render figure ---
        import textwrap as _tw
        wrapped = _tw.fill(ai_text, width=72)

        fig = plt.figure(figsize=(10, 4.2))
        fig.patch.set_facecolor('#0d1117')
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor('#0d1117')
        ax.axis('off')

        # Header strip
        ax.add_patch(plt.Rectangle([0.03, 0.70], 0.94, 0.24,
                                    facecolor='#161b22', edgecolor='#30363d',
                                    linewidth=1.2, transform=ax.transAxes, clip_on=False))
        ax.text(0.5, 0.84,
                '40. AI Weekly Digest — Еженедельный дайджест борды',
                transform=ax.transAxes, fontsize=13, fontweight='bold',
                color='#58a6ff', ha='center', va='center')

        # Stats strip
        stats_line = (
            f"[ Постов: {posts_7d:,} ]   [ Авторов: {uniq_7d} ]   "
            f"[ Топ: {top_author.split('(')[0].strip()} ]   [ Токсичность: {toxic_pct}% ]"
        )
        ax.text(0.5, 0.74, stats_line,
                transform=ax.transAxes, fontsize=8.5,
                color='#39d353', ha='center', va='center', fontweight='bold')

        # AI text body
        ax.text(0.5, 0.38, wrapped,
                transform=ax.transAxes, fontsize=10.5,
                color='#e6edf3', ha='center', va='center',
                linespacing=1.55)

        # Footer
        ax.text(0.5, 0.05,
                f'ИИ-модель: Groq {model_used}  |  Данные: 7 дней  |  Генерация: раз в неделю',
                transform=ax.transAxes, fontsize=7.5,
                color='#484f58', ha='center', va='bottom')

        save_chart(images, '40_ai_digest.png')
    except Exception as e:
        print(f"Error Chart 40: {e}")


def generate_all_charts():
    """Generates exactly 10 toxic charts and returns a list of io.BytesIO objects"""
    # pyplot глобален, а генераторов графиков в боте три и все в пулах потоков.
    # Без замка параллельный /graph перетирал тему прямо посреди отрисовки.
    with matplotlib_guard():
        apply_dark_theme()
        return _generate_all_charts_locked()


def _generate_all_charts_locked():
    thirty_days_ago = time.time() - (30 * 24 * 3600)
    images = []
    edges_data = None

    with contextlib.closing(connect_stats_db()) as conn:
        conn.row_factory = dict_factory
        with contextlib.closing(conn.cursor()) as c:
            try:
                _generate_chart_1(thirty_days_ago, c, images)
                _generate_chart_2(c, images)
                _generate_chart_3(thirty_days_ago, c, images)
                _generate_chart_4(thirty_days_ago, c, images)
                _generate_chart_5(thirty_days_ago, c, images)
                _generate_chart_6(thirty_days_ago, c, images)
                _generate_chart_7(thirty_days_ago, c, images)
                _generate_chart_8(thirty_days_ago, c, images)
                _generate_chart_9(thirty_days_ago, c, images)
                _generate_chart_10(thirty_days_ago, c, images)
                edges_data = _generate_chart_11(thirty_days_ago, c, images)
                _generate_chart_12(edges_data, images)
                _generate_chart_13(edges_data, images)
                _generate_chart_14(thirty_days_ago, c, images)
                _generate_chart_15(c, images)
                _generate_chart_16(thirty_days_ago, c, images)
                _generate_chart_17(thirty_days_ago, c, images)
                _generate_chart_18(thirty_days_ago, c, images)
                _generate_chart_19(thirty_days_ago, c, images)
                _generate_chart_20(thirty_days_ago, c, images)
                _generate_chart_21(c, images)
                _generate_chart_22(c, images)
                _generate_chart_23(c, images)
                _generate_chart_24(c, images)
                _generate_chart_25(c, images)
                _generate_chart_26(c, images)
                _generate_chart_27(images)
                _generate_chart_28(c, images)
                _generate_chart_29(images)
                _generate_chart_30(images)
                _generate_chart_31(images)
                _generate_chart_32(images)
                _generate_chart_33(c, images)
                _generate_chart_34(c, images)
                _generate_chart_35(c, images)
                _generate_chart_36(c, images)
                _generate_chart_37(c, images)
                _generate_chart_38(c, images)
                _generate_chart_39(c, images)
                _generate_chart_40(images)
            except Exception as e:
                print(f"Error generating charts: {e}")

    return images


def fetch_user_stats_data(user_id: int, board_id: str) -> dict:
    with contextlib.closing(connect_stats_db()) as conn:
        with contextlib.closing(conn.cursor()) as c:

            # 1. Fetch user profile
            c.execute("SELECT balance, role, created_at, lie_media, custom_prefix FROM Users WHERE user_id = ? AND board_id = ?", (user_id, board_id))
            profile = c.fetchone()
            if profile:
                balance, role, created_at, lie_media, custom_prefix = profile
            else:
                balance, role, created_at, lie_media, custom_prefix = 0.0, 'user', time.time(), 0, None

            # 2. Count actual posts
            c.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ? AND board_id = ?", (user_id, board_id))
            posts_count = c.fetchone()[0]

            # 3. Count reactions received
            c.execute("""
                SELECT COUNT(*) FROM ReactionQueue rq
                JOIN Posts p ON rq.post_num = p.post_num
                WHERE p.author_id = ? AND p.board_id = ?
            """, (user_id, board_id))
            rx_received = c.fetchone()[0]

            # 4. Count reactions given
            c.execute("SELECT COUNT(*) FROM ReactionQueue WHERE user_id = ?", (user_id,))
            rx_given = c.fetchone()[0]

            # 5. Count mutes
            c.execute("SELECT COUNT(*) FROM Mutes WHERE user_id = ? AND board_id = ?", (user_id, board_id))
            mutes_count = c.fetchone()[0]

            # 6. Rank among other users on this board
            c.execute("""
                SELECT user_id FROM Users
                WHERE board_id = ?
                ORDER BY posts_count DESC, balance DESC;
            """, (board_id,))
            all_users = [r[0] for r in c]
            try:
                rank = all_users.index(user_id) + 1
            except ValueError:
                rank = len(all_users) + 1


            return {
                'balance': balance,
                'role': role,
                'created_at': created_at,
                'lie_media': lie_media,
                'custom_prefix': custom_prefix,
                'posts_count': posts_count,
                'rx_received': rx_received,
                'rx_given': rx_given,
                'mutes_count': mutes_count,
                'rank': rank,
                'total_users': len(all_users)
            }


def _get_role_name(role: str) -> str:
    return {
        'admin': 'Админ',
        'mod': 'Модератор',
        'janitor': 'Дворник',
        'user': 'Анон'
    }.get(role, 'Анон')

def _get_slang_comment(posts_count: int, rank: int, balance: float) -> str:
    if posts_count == 0:
        return "Ньюфаг детектед. Иди читай правила борды, анон."
    elif rank <= 3:
        return "ОП-хуй и бог тредов! База сертифицирована, скуфы падают ниц."
    elif posts_count > 300:
        return "Почетный Скуф борды. Запах подпиваса и базированных мыслей за версту."
    elif balance < 10:
        return "Нищук детектед. Проиграл все коины в рулетку или забанен за сажу."
    else:
        return "Обычный сыч. Бамп в тред, сажу в комменты."

@dataclass
class CardConfig:
    x: int
    y: int
    w: int
    h: int
    val: str
    label: str
    color: str

@dataclass
class UserStatsCardData:
    user_id: int
    board_id: str
    schizo_name: str
    role_name: str
    custom_prefix: str
    role: str
    posts_count: int
    rx_received: int
    rx_given: int
    mutes_count: int
    balance: float
    lie_media: float
    rank: int
    total_users: int
    slang_comment: str


def _format_text_report(data: UserStatsCardData) -> str:
    return (
        f"☘️ <b>Статистика пользователя {data.schizo_name}</b> (/${data.board_id}/)\n\n"
        f"👤 <b>Статус:</b> {data.role_name} {f'({data.custom_prefix})' if data.custom_prefix else ''}\n"
        f"🏅 <b>Ранг борды:</b> #{data.rank} из {data.total_users}\n"
        f"📝 <b>Написано постов:</b> {data.posts_count}\n"
        f"🎭 <b>Получено реакций:</b> +{data.rx_received}\n"
        f"⚡ <b>Поставлено реакций:</b> {data.rx_given}\n"
        f"💰 <b>Баланс:</b> {int(data.balance)} RUB\n"
        f"🔇 <b>Схвачено мутов:</b> {data.mutes_count}\n"
        f"🌀 <b>Кринж-фактор:</b> {data.lie_media}%\n\n"
        f"💬 <i>\"{data.slang_comment}\"</i>"
    )

def generate_user_stats_card(user_id: int, board_id: str, username: str) -> tuple[io.BytesIO, str]:
    stats_data = fetch_user_stats_data(user_id, board_id)

    schizo_name = generate_schizo_name(user_id)
    role_name = _get_role_name(stats_data['role'])
    slang_comment = _get_slang_comment(stats_data['posts_count'], stats_data['rank'], stats_data['balance'])

    card_data = UserStatsCardData(
        user_id=user_id,
        board_id=board_id,
        schizo_name=schizo_name,
        role_name=role_name,
        custom_prefix=stats_data['custom_prefix'],
        role=stats_data['role'],
        posts_count=stats_data['posts_count'],
        rx_received=stats_data['rx_received'],
        rx_given=stats_data['rx_given'],
        mutes_count=stats_data['mutes_count'],
        balance=stats_data['balance'],
        lie_media=stats_data['lie_media'],
        rank=stats_data['rank'],
        total_users=stats_data['total_users'],
        slang_comment=slang_comment
    )

    text_report = _format_text_report(card_data)
    buf = draw_user_stats_card(card_data)
    return buf, text_report



def draw_user_stats_card(
    data: UserStatsCardData
) -> io.BytesIO:
    import os
    from PIL import Image, ImageDraw, ImageFont

    width, height = 800, 450
    img = Image.new('RGB', (width, height), color='#0d0f12')
    draw = ImageDraw.Draw(img)

    try:
        font_path = "font1.ttf" if os.path.exists("font1.ttf") else "arial.ttf"
        font_title = ImageFont.truetype(font_path, 26)
        font_subtitle = ImageFont.truetype(font_path, 15)
        font_card_num = ImageFont.truetype(font_path, 22)
        font_card_lbl = ImageFont.truetype(font_path, 12)
        font_comment = ImageFont.truetype(font_path, 14)
    except Exception:
        font_title = font_subtitle = font_card_num = font_card_lbl = font_comment = ImageFont.load_default()

    # Header bar
    draw.rectangle([0, 0, width, 95], fill='#13171f')
    draw.line([0, 95, width, 95], fill='#252932', width=2)

    # Title & Info
    draw.text((30, 22), data.schizo_name, fill='#ff9900', font=font_title)
    status_text = f"ID: {data.user_id}  |  Раздел: /{data.board_id}/  |  Статус: {data.role_name} {f'({data.custom_prefix})' if data.custom_prefix else ''}"
    draw.text((30, 60), status_text, fill='#8abeb7', font=font_subtitle)

    # Certified badge (top right)
    draw.rounded_rectangle([610, 15, 770, 80], radius=6, fill='#1b1f28', outline='#ff9900', width=2)
    draw.text((690, 33), "ТГАЧ CERTIFIED", fill='#ff9900', font=font_subtitle, anchor="mm")
    sub_cert = "APPROVED BITYARD" if data.role != 'admin' else "ADMINISTRATOR"
    draw.text((690, 58), sub_cert, fill='#00ffcc', font=ImageFont.truetype(font_path, 10) if os.path.exists(font_path) else font_subtitle, anchor="mm")

    # Helper to draw cards
    def draw_card(cfg: CardConfig):
        draw.rounded_rectangle([cfg.x, cfg.y, cfg.x+cfg.w, cfg.y+cfg.h], radius=6, fill='#13171f', outline='#252932', width=1)
        draw.ellipse([cfg.x+15, cfg.y+16, cfg.x+23, cfg.y+24], fill=cfg.color)
        draw.text((cfg.x+33, cfg.y+20), cfg.label, fill='#969896', font=font_card_lbl, anchor="lm")
        draw.text((cfg.x+15, cfg.y+48), cfg.val, fill=cfg.color, font=font_card_num, anchor="lm")

    # Cards grid
    cards = [
        CardConfig(30, 115, 175, 80, str(data.posts_count), "Написано постов", "#00ffcc"),
        CardConfig(220, 115, 175, 80, f"#{data.rank} / {data.total_users}", "Ранг на борде", "#ffcc00"),
        CardConfig(410, 115, 175, 80, f"{int(data.balance)} RUB", "Баланс коинов", "#00ff66"),

        CardConfig(30, 210, 175, 80, f"+{data.rx_received}", "Получено реакций", "#ff3399"),
        CardConfig(220, 210, 175, 80, str(data.rx_given), "Поставлено реакций", "#859900"),
        CardConfig(410, 210, 175, 80, f"{data.lie_media}%", "Кринж-фактор", "#cc00ff"),
    ]

    for card in cards:
        draw_card(card)

    # Mutes Card (top right block)
    draw.rounded_rectangle([600, 115, 770, 175], radius=6, fill='#1d1315', outline='#ff3333', width=1)
    draw.ellipse([600+15, 115+16, 600+23, 115+24], fill="#ff3333")
    draw.text((600+33, 115+20), "Схвачено мутов", fill='#969896', font=font_card_lbl, anchor="lm")
    draw.text((600+15, 115+48), f"{data.mutes_count} шт", fill="#ff3339", font=font_card_num, anchor="lm")

    # Activity Level Card (below mutes)
    draw.rounded_rectangle([600, 210, 770, 290], radius=6, fill='#13171f', outline='#252932', width=1)
    draw.text((615, 230), "Уровень деградации", fill='#969896', font=font_card_lbl)
    activity_pct = min(1.0, data.posts_count / 500.0)
    draw.rounded_rectangle([615, 255, 755, 267], radius=3, fill='#1b1f28')
    draw.rounded_rectangle([615, 255, 615 + int(140 * activity_pct), 267], radius=3, fill='#ff9900')
    draw.text((755, 230), f"{int(activity_pct*100)}%", fill='#ff9900', font=font_card_lbl, anchor="ra")

    # Bottom Summary Box
    draw.rounded_rectangle([30, 310, 770, 420], radius=8, fill='#1b1f28', outline='#252932', width=1)
    draw.text((50, 335), "РЕЗЮМЕ ДЕГРАДАЦИИ:", fill='#ff9900', font=font_card_lbl)

    # Wrap comment safely
    import textwrap
    wrapped_lines = textwrap.wrap(f'"{data.slang_comment}"', width=90)
    y_comm = 360
    for line in wrapped_lines[:2]:
        draw.text((50, y_comm), line, fill='#e6edf3', font=font_comment)
        y_comm += 20

    buf = io.BytesIO()
    img.save(buf, format='png')
    buf.seek(0)
    return buf

if __name__ == "__main__":
    imgs = generate_all_charts()
    print(f"Generated {len(imgs)} toxic charts successfully.")
