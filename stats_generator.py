import sqlite3
import time
import json
import io
import random
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import pandas as pd

# Use non-interactive backend
matplotlib.use('Agg')

# Set dark theme for imageboard vibes
plt.style.use('dark_background')
sns.set_theme(style="darkgrid", rc={
    "axes.facecolor": "#121212", 
    "figure.facecolor": "#121212",
    "text.color": "#FFFFFF",
    "axes.labelcolor": "#FFFFFF",
    "xtick.color": "#FFFFFF",
    "ytick.color": "#FFFFFF",
    "grid.color": "#333333",
    "font.family": "sans-serif"
})

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

NICK_PREFIXES = ["Шиз", "Аутист", "Дед", "Попущ", "Биомусор", "Анон", "Гигачад", "Школьник", "Скуф", "Сыч", "Альтушка", "Тролль", "Омежка"]
NICK_SUFFIXES = ["Интеллектуал", "Качалка", "Пердед", "Шпана", "Ноулайфер", "Шизофреник", "Анимешник", "Говнопостер", "Таксист", "Подпивас", "Куколд", "Скуфидон"]

def generate_schizo_name(user_id: int) -> str:
    if not user_id: return "Анонимус"
    random.seed(user_id)
    prefix = random.choice(NICK_PREFIXES)
    suffix = random.choice(NICK_SUFFIXES)
    return f"{prefix}-{suffix} (#{str(user_id)[-4:]})"

def generate_provocateur_name(user_id: int) -> str:
    if not user_id: return "Анонимус"
    random.seed(user_id + 999) # different seed to vary names
    titles = ["Байтер", "Жертва Буллинга", "Провокатор", "Корм для Троллей", "Клоун"]
    return f"{random.choice(titles)} (#{str(user_id)[-4:]})"

def _generate_posts_per_day(c, thirty_days_ago):
    c.execute('''
        SELECT date(timestamp, 'unixepoch', 'localtime') as d, COUNT(*) as cnt 
        FROM Posts 
        WHERE timestamp > ? 
        GROUP BY d ORDER BY d
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=df, x='d', y='cnt', marker="o", color="#ff3366", ax=ax)
    plt.title('1. Объем высеров (Посты по дням)', fontsize=16, fontweight='bold', color="#ff3366")
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('1_posts.png', buf)

def _generate_weekly_active_users(c):
    c.execute('''
        SELECT strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as week, COUNT(DISTINCT author_id) as cnt 
        FROM Posts 
        WHERE timestamp > ? 
        GROUP BY week ORDER BY week
    ''', (time.time() - (60 * 24 * 3600),)) # 60 days to show weekly trends better
    data = c.fetchall()
    if not data:
        return None
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=df, x='week', y='cnt', color="#00ffcc", ax=ax)
    plt.title('2. Размер онлайна (Уникальные шизы за НЕДЕЛЮ)', fontsize=16, fontweight='bold', color="#00ffcc")
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('2_wau.png', buf)

def _generate_toxicity_chart(c, thirty_days_ago):
    c.execute('''
        SELECT date(timestamp, 'unixepoch', 'localtime') as d, content 
        FROM Posts 
        WHERE timestamp > ? 
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    daily_stats = {}
    swear_roots = ['хуй', 'хуе', 'хуя', 'бля', 'пизд', 'еба', 'пидор', 'гандон', 'шлюх', 'мудак']

    for r in data:
        d = r['d']
        if d not in daily_stats:
            daily_stats[d] = {'total': 0, 'toxic': 0}
        
        daily_stats[d]['total'] += 1
        content_lower = r['content'].lower()
        if any(root in content_lower for root in swear_roots):
            daily_stats[d]['toxic'] += 1
            
    plot_data = []
    for d, stats in sorted(daily_stats.items()):
        toxic_percent = (stats['toxic'] / stats['total']) * 100 if stats['total'] > 0 else 0
        plot_data.append({'d': d, 'toxic_percent': toxic_percent})

    df = pd.DataFrame(plot_data)
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=df, x='d', y='toxic_percent', marker="X", color="#ff0000", ax=ax)
    ax.fill_between(df['d'], df['toxic_percent'], color="#ff0000", alpha=0.3)
    plt.title('3. Матоемкость (% постов с матами)', fontsize=16, fontweight='bold', color="#ff0000")
    plt.ylabel('% постов с матом')
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('3_toxicity.png', buf)

def _generate_top_schizos(c, thirty_days_ago):
    c.execute('''
        SELECT author_id, COUNT(*) as cnt 
        FROM Posts 
        WHERE author_id IS NOT NULL AND timestamp > ?
        GROUP BY author_id ORDER BY cnt DESC LIMIT 10
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    df = pd.DataFrame(data)
    df['author_name'] = df['author_id'].apply(generate_schizo_name)
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=df, y='author_name', x='cnt', hue='author_name', palette="magma", legend=False, ax=ax)
    plt.title('4. Топ-10 Главных Шизоидов (По количеству высеров)', fontsize=16, fontweight='bold', color="#ff9900")
    plt.xlabel('Количество постов')
    plt.ylabel('')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('4_top_schizos.png', buf)

def _generate_provocateurs(c, thirty_days_ago):
    c.execute('''
        SELECT orig.author_id, COUNT(*) as cnt 
        FROM Posts repl
        JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
        WHERE repl.timestamp > ? AND orig.author_id IS NOT NULL
        GROUP BY orig.author_id ORDER BY cnt DESC LIMIT 5
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    df = pd.DataFrame(data)
    df['author_name'] = df['author_id'].apply(generate_provocateur_name)
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.barplot(data=df, y='author_name', x='cnt', hue='author_name', palette="viridis", legend=False, ax=ax)
    plt.title('5. Главные Байтеры (Кому больше всего реплаят)', fontsize=16, fontweight='bold', color="#33ccff")
    plt.xlabel('Количество полученных ответов')
    plt.ylabel('')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('5_provocateurs.png', buf)

def _generate_post_length_hist(c, thirty_days_ago):
    c.execute('''
        SELECT content FROM Posts WHERE timestamp > ?
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    lengths = []
    for r in data:
        try:
            content_dict = json.loads(r['content'])
            text = content_dict.get('text') or content_dict.get('caption') or ''
            if text:
                lengths.append(len(text))
        except:
            pass

    if not lengths:
        return None
    df = pd.DataFrame({'length': lengths})
    df = df[df['length'] < 1000]
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(df['length'], bins=50, color="#cc00ff", kde=True, ax=ax)
    plt.title('6. Формат общения (Длина постов)', fontsize=16, fontweight='bold', color="#cc00ff")
    plt.xlabel('Длина текста (символы)')
    plt.ylabel('Количество постов')
    plt.axvline(x=20, color='r', linestyle='--')
    plt.text(25, ax.get_ylim()[1]*0.9, 'Одноклеточные (<20)', color='r')
    plt.axvline(x=300, color='g', linestyle='--')
    plt.text(310, ax.get_ylim()[1]*0.8, 'Пасто-писатели (>300)', color='g')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('6_post_length.png', buf)

def _generate_night_owls(c, thirty_days_ago):
    c.execute('''
        SELECT 
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as night_posts,
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) NOT BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as day_posts
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if not row or not (row['night_posts'] or row['day_posts']):
        return None
    labels = ['Ночь (01:00-06:00)', 'Остальное время']
    sizes = [row['night_posts'] or 0, row['day_posts'] or 0]
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=["#6600cc", "#ffcc00"])
    plt.title('7. Клуб Полуночников', fontsize=16, fontweight='bold')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('7_night_owls.png', buf)

def _generate_media_dependency(c, thirty_days_ago):
    c.execute('''
        SELECT 
            SUM(CASE WHEN content LIKE '%"type": "text"%' THEN 1 ELSE 0 END) as text_posts,
            SUM(CASE WHEN content LIKE '%"type": "photo"%' OR content LIKE '%"type": "video"%' THEN 1 ELSE 0 END) as media_posts
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if not row or not (row['text_posts'] or row['media_posts']):
        return None
    labels = ['Текст (Голый текст)', 'Медиа (Пикчи/Видео)']
    sizes = [row['text_posts'] or 0, row['media_posts'] or 0]
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=["#cccccc", "#ff3399"])
    plt.title('8. Картинкодрочеры vs Текстовики', fontsize=16, fontweight='bold')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('8_media.png', buf)

def _generate_discussion_level(c, thirty_days_ago):
    c.execute('''
        SELECT 
            SUM(CASE WHEN reply_to_post_num IS NOT NULL THEN 1 ELSE 0 END) as replies,
            SUM(CASE WHEN reply_to_post_num IS NULL THEN 1 ELSE 0 END) as singles
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if not row or not (row['replies'] or row['singles']):
        return None
    labels = ['Реплаи (Диалог/Срач)', 'Отдельные посты (Крик в пустоту)']
    sizes = [row['replies'] or 0, row['singles'] or 0]
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=45, colors=["#00ff99", "#555555"])
    plt.title('9. Уровень Дискуссии', fontsize=16, fontweight='bold')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('9_dialogs.png', buf)

def _generate_activity_heatmap(c, thirty_days_ago):
    c.execute('''
        SELECT cast(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as w, 
               cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h, 
               COUNT(*) as cnt 
        FROM Posts 
        WHERE timestamp > ? 
        GROUP BY w, h
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if not data:
        return None
    df = pd.DataFrame(data)
    heatmap_data = df.pivot(index="w", columns="h", values="cnt").fillna(0)
    # Weekdays: 0=Sunday in SQLite strftime('%w')
    weekdays = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
    # Fill missing weekdays if any
    for i in range(7):
        if i not in heatmap_data.index:
            heatmap_data.loc[i] = 0
    heatmap_data = heatmap_data.sort_index()
    heatmap_data.index = weekdays

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(heatmap_data, cmap="inferno", linewidths=.5, ax=ax)
    plt.title('10. Тепловая карта активности (Часы / Дни)', fontsize=16, fontweight='bold', color="#ffaa00")
    plt.xlabel('Час (МСК)')
    plt.ylabel('День недели')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return ('10_heatmap.png', buf)

def generate_all_charts():
    """Generates exactly 10 toxic charts and returns a list of io.BytesIO objects"""
    conn = sqlite3.connect('dvach_bot.db', uri=True)
    conn.row_factory = dict_factory
    c = conn.cursor()

    thirty_days_ago = time.time() - (30 * 24 * 3600)
    images = []

    # Generate all charts
    chart_generators = [
        lambda: _generate_posts_per_day(c, thirty_days_ago),
        lambda: _generate_weekly_active_users(c),
        lambda: _generate_toxicity_chart(c, thirty_days_ago),
        lambda: _generate_top_schizos(c, thirty_days_ago),
        lambda: _generate_provocateurs(c, thirty_days_ago),
        lambda: _generate_post_length_hist(c, thirty_days_ago),
        lambda: _generate_night_owls(c, thirty_days_ago),
        lambda: _generate_media_dependency(c, thirty_days_ago),
        lambda: _generate_discussion_level(c, thirty_days_ago),
        lambda: _generate_activity_heatmap(c, thirty_days_ago)
    ]

    for generator in chart_generators:
        result = generator()
        if result:
            images.append(result)

    conn.close()
    return images

if __name__ == "__main__":
    imgs = generate_all_charts()
    print(f"Generated {len(imgs)} toxic charts successfully.")
