import sqlite3
import time
import json
import io
import random
import re
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
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

NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]

def generate_schizo_name(user_id: int) -> str:
    if not user_id: return "Анонимус"
    rng = random.Random(user_id)
    prefix = rng.choice(NICK_PREFIXES)
    suffix = rng.choice(NICK_SUFFIXES)
    return f"{prefix}-{suffix} (#{str(user_id)[-4:]})"

def _generate_chart_1(c, thirty_days_ago, images):
    """1. Объем высеров (Posts per day)"""
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
        sns.lineplot(data=df, x='d', y='cnt', marker="o", color="#ff3366", ax=ax)
        plt.title('1. Объем высеров (Посты по дням)', fontsize=16, fontweight='bold', color="#ff3366")
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('1_posts.png', buf))
        plt.close()

def _generate_chart_2(c, thirty_days_ago, images):
    """2. Уникальные шизы (Weekly Active Users)"""
    c.execute('''
        SELECT strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as week, COUNT(DISTINCT author_id) as cnt 
        FROM Posts 
        WHERE timestamp > ? 
        GROUP BY week ORDER BY week
    ''', (time.time() - (60 * 24 * 3600),)) # 60 days to show weekly trends better
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.barplot(data=df, x='week', y='cnt', color="#00ffcc", ax=ax)
        plt.title('2. Размер онлайна (Уникальные шизы за НЕДЕЛЮ)', fontsize=16, fontweight='bold', color="#00ffcc")
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('2_wau.png', buf))
        plt.close()

def _generate_chart_3(c, thirty_days_ago, images):
    """3. Матоемкость борды"""
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
        images.append(('3_toxicity.png', buf))
        plt.close()

def _generate_chart_4(c, thirty_days_ago, images):
    """4. Топ-10 Главных Шизоидов"""
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
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('4_top_schizos.png', buf))
        plt.close()

def _generate_chart_5(c, thirty_days_ago, images):
    """5. Главные Провокаторы (Топ-5 юзеров, кому больше всего отвечают)"""
    c.execute('''
        SELECT orig.author_id, COUNT(*) as cnt 
        FROM Posts repl
        JOIN Posts orig ON repl.reply_to_post_num = orig.post_num AND repl.board_id = orig.board_id
        WHERE repl.timestamp > ? AND orig.author_id IS NOT NULL
        GROUP BY orig.author_id ORDER BY cnt DESC LIMIT 5
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        df = pd.DataFrame(data)
        df['author_name'] = df['author_id'].apply(generate_schizo_name)
        fig, ax = plt.subplots(figsize=(10, 4))
        sns.barplot(data=df, y='author_name', x='cnt', hue='author_name', palette="viridis", legend=False, ax=ax)
        plt.title('5. Главные Байтеры (Кому больше всего реплаят)', fontsize=16, fontweight='bold', color="#33ccff")
        plt.xlabel('Количество полученных ответов')
        plt.ylabel('')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('5_provocateurs.png', buf))
        plt.close()

def _generate_chart_6(c, thirty_days_ago, images):
    """6. Гистограмма длины постов (Одноклеточные vs Пасты)"""
    c.execute('''
        SELECT content FROM Posts WHERE timestamp > ?
    ''', (thirty_days_ago,))
    data = c.fetchall()
    if data:
        lengths = []
        for r in data:
            try:
                content_dict = json.loads(r['content'])
                text = content_dict.get('text') or content_dict.get('caption') or ''
                if text:
                    lengths.append(len(text))
            except:
                pass
        
        if lengths:
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
            images.append(('6_post_length.png', buf))
            plt.close()

def _generate_chart_7(c, thirty_days_ago, images):
    """7. Клуб Полуночников (Night vs Day)"""
    c.execute('''
        SELECT 
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as night_posts,
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) NOT BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as day_posts
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if row and (row['night_posts'] or row['day_posts']):
        labels = ['Ночь (01:00-06:00)', 'Остальное время']
        sizes = [row['night_posts'] or 0, row['day_posts'] or 0]
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=["#6600cc", "#ffcc00"])
        plt.title('7. Клуб Полуночников', fontsize=16, fontweight='bold')
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('7_night_owls.png', buf))
        plt.close()

def _generate_chart_8(c, thirty_days_ago, images):
    """8. Медиа-зависимость (Картинкодрочеры vs Текстовики)"""
    c.execute('''
        SELECT 
            SUM(CASE WHEN content LIKE '%"type": "text"%' THEN 1 ELSE 0 END) as text_posts,
            SUM(CASE WHEN content LIKE '%"type": "photo"%' OR content LIKE '%"type": "video"%' THEN 1 ELSE 0 END) as media_posts
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if row and (row['text_posts'] or row['media_posts']):
        labels = ['Текст (Голый текст)', 'Медиа (Пикчи/Видео)']
        sizes = [row['text_posts'] or 0, row['media_posts'] or 0]
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90, colors=["#cccccc", "#ff3399"])
        plt.title('8. Картинкодрочеры vs Текстовики', fontsize=16, fontweight='bold')
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('8_media.png', buf))
        plt.close()

def _generate_chart_9(c, thirty_days_ago, images):
    """9. Уровень дискуссии (Реплаи vs Крик в пустоту)"""
    c.execute('''
        SELECT 
            SUM(CASE WHEN reply_to_post_num IS NOT NULL THEN 1 ELSE 0 END) as replies,
            SUM(CASE WHEN reply_to_post_num IS NULL THEN 1 ELSE 0 END) as singles
        FROM Posts 
        WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row = c.fetchone()
    if row and (row['replies'] or row['singles']):
        labels = ['Реплаи (Диалог/Срач)', 'Отдельные посты (Крик в пустоту)']
        sizes = [row['replies'] or 0, row['singles'] or 0]
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=45, colors=["#00ff99", "#555555"])
        plt.title('9. Уровень Дискуссии', fontsize=16, fontweight='bold')
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('9_dialogs.png', buf))
        plt.close()

def _generate_chart_10(c, thirty_days_ago, images):
    """10. Тепловая карта активности (Heatmap)"""
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
        images.append(('10_heatmap.png', buf))
        plt.close()

def _generate_chart_11(c, thirty_days_ago, images):
    """11. Граф Социального Пузыря (Echo Chambers)"""
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
                top_nodes = [node for node, degree in sorted(G.degree(), key=lambda x: x[1], reverse=True)[:100]]
                G_sub = G.subgraph(top_nodes).copy()
                
                communities = nx.community.louvain_communities(G_sub)
                community_map = {}
                for i, comm in enumerate(communities):
                    for node in comm:
                        community_map[node] = i
                        
                colors = [community_map.get(node, 0) for node in G_sub.nodes()]
                
                fig, ax = plt.subplots(figsize=(10, 8))
                pos = nx.spring_layout(G_sub, k=0.18, seed=42)
                
                nx.draw_networkx_nodes(G_sub, pos, node_size=120, node_color=colors, cmap=plt.cm.tab20, ax=ax)
                nx.draw_networkx_edges(G_sub, pos, alpha=0.3, edge_color='#555555', ax=ax)
                
                plt.title('11. Граф Социального Пузыря (Эхо-камеры)', fontsize=16, fontweight='bold', color="#00ffcc")
                ax.axis('off')
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('11_echo_chambers.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 11: {e}")

def _generate_chart_12(c, thirty_days_ago, images):
    """12. Топ-10 Хабов Внимания (PageRank Centrality)"""
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
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('12_pagerank.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 12: {e}")

def _generate_chart_13(c, thirty_days_ago, images):
    """13. Коэффициент Взаимного Дроча (Circlejerk Index)"""
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
                sorted_mutual = sorted(mutual_list, key=lambda x: x[2], reverse=True)[:5]
                plot_data = []
                for u, v, rec in sorted_mutual:
                    name_u = generate_schizo_name(u)
                    name_v = generate_schizo_name(v)
                    plot_data.append({'pair': f"{name_u} & {name_v}", 'score': rec})
                    
                df_mut = pd.DataFrame(plot_data)
                fig, ax = plt.subplots(figsize=(10, 4))
                sns.barplot(data=df_mut, y='pair', x='score', hue='pair', palette="spring", legend=False, ax=ax)
                plt.title('13. Топ-5 Взаимных Перепихонов (Circlejerk)', fontsize=16, fontweight='bold', color="#00ff66")
                plt.xlabel('Количество взаимных ответов друг другу')
                plt.ylabel('')
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('13_circlejerk.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 13: {e}")

def _generate_chart_14(c, thirty_days_ago, images):
    """14. Сессионный Анализ (Длина сессий)"""
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
                df_sess = pd.DataFrame({'duration': session_durations})
                df_sess = df_sess[df_sess['duration'] < 180]
                
                fig, ax = plt.subplots(figsize=(10, 5))
                sns.histplot(df_sess['duration'], bins=30, color="#ff9933", kde=True, ax=ax)
                plt.title('14. Длина непрерывного залипания (Сессии)', fontsize=16, fontweight='bold', color="#ff9933")
                plt.xlabel('Длительность сессии (минуты, лимит 15 мин на паузу)')
                plt.ylabel('Количество сессий')
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('14_sessions.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 14: {e}")

def _generate_chart_15(c, thirty_days_ago, images):
    """15. Ритмы Выгорания (Автокорреляция топ-постера)"""
    try:
        c.execute('''
            SELECT author_id, COUNT(*) as cnt 
            FROM Posts 
            WHERE timestamp > ? AND author_id IS NOT NULL
            GROUP BY author_id ORDER BY cnt DESC LIMIT 1
        ''', (thirty_days_ago,))
        top_author_row = c.fetchone()
        if top_author_row:
            top_uid = top_author_row['author_id']
            c.execute('''
                SELECT timestamp FROM Posts 
                WHERE author_id = ? AND timestamp > ?
                ORDER BY timestamp
            ''', (top_uid, thirty_days_ago))
            top_times = [r['timestamp'] for r in c.fetchall()]
            
            if len(top_times) > 50:
                min_ts = thirty_days_ago
                max_ts = time.time()
                total_hours = int((max_ts - min_ts) / 3600) + 1
                
                hourly_counts = [0] * total_hours
                for ts in top_times:
                    hour_bin = int((ts - min_ts) / 3600)
                    if 0 <= hour_bin < total_hours:
                        hourly_counts[hour_bin] += 1
                        
                ts_series = pd.Series(hourly_counts)
                lags = list(range(1, 49))
                acf_values = [ts_series.autocorr(lag=l) for l in lags]
                acf_values = [0 if pd.isna(v) else v for v in acf_values]
                
                df_acf = pd.DataFrame({'lag': lags, 'correlation': acf_values})
                fig, ax = plt.subplots(figsize=(10, 5))
                sns.lineplot(data=df_acf, x='lag', y='correlation', marker="o", color="#33cc99", ax=ax)
                plt.title(f'15. Циркадные биоритмы топ-постера {generate_schizo_name(top_uid).split(" (")[0]}', fontsize=16, fontweight='bold', color="#33cc99")
                plt.xlabel('Сдвиг во времени (лаг, часы)')
                plt.ylabel('Автокорреляция')
                plt.axvline(x=24, color='r', linestyle='--', alpha=0.7, label='24 часа')
                plt.axhline(y=0, color='grey', linestyle='-', alpha=0.5)
                plt.legend()
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('15_autocorrelation.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 15: {e}")

def _generate_chart_16(c, thirty_days_ago, images):
    """16. Тематическое Моделирование (LDA)"""
    try:
        c.execute('''
            SELECT content FROM Posts 
            WHERE timestamp > ? AND content IS NOT NULL
            ORDER BY timestamp DESC LIMIT 5000
        ''', (thirty_days_ago,))
        lda_data = c.fetchall()
        if lda_data:
            texts = []
            for r in lda_data:
                try:
                    content_dict = json.loads(r['content'])
                    t = content_dict.get('text') or content_dict.get('caption') or ''
                    if len(t.strip()) > 10:
                        texts.append(t)
                except:
                    pass
                    
            if len(texts) > 50:
                from sklearn.feature_extraction.text import CountVectorizer
                from sklearn.decomposition import LatentDirichletAllocation
                
                ru_stop = [
                    'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты',
                    'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'уже',
                    'до', 'этого', 'этой', 'эти', 'эту', 'это', 'тот', 'где', 'кто', 'он', 'мы', 'быть', 'был', 'была', 'были', 'было', 'есть',
                    'если', 'или', 'ком', 'всех', 'них', 'этот', 'чтобы', 'для', 'без', 'через', 'после', 'потому', 'этом', 'им', 'ей',
                    'про', 'почему', 'зачем', 'очень', 'просто', 'тут', 'там', 'когда', 'будет', 'даже', 'всегда', 'тоже',
                    'какой', 'какая', 'какие', 'свои', 'свой', 'своих', 'под', 'над', 'перед', 'при', 'всего', 'всем', 'всеми', 'тебе', 'вас'
                ]
                
                vectorizer = CountVectorizer(max_df=0.85, min_df=2, max_features=800, stop_words=ru_stop)
                tf = vectorizer.fit_transform(texts)
                
                lda = LatentDirichletAllocation(n_components=5, max_iter=8, random_state=42, n_jobs=1)
                lda.fit(tf)
                
                feature_names = vectorizer.get_feature_names_out()
                
                fig, axes = plt.subplots(5, 1, figsize=(10, 12), sharex=False)
                colors_palette = sns.color_palette("muted", 5)
                
                for topic_idx, topic in enumerate(lda.components_):
                    top_features_ind = topic.argsort()[:-8:-1]
                    top_features = [feature_names[i] for i in top_features_ind]
                    weights = [topic[i] for i in top_features_ind]
                    
                    ax = axes[topic_idx]
                    sns.barplot(x=weights, y=top_features, color=colors_palette[topic_idx], ax=ax)
                    ax.set_title(f"Тема {topic_idx + 1}", fontsize=12, fontweight='bold')
                    ax.tick_params(labelsize=10)
                    
                plt.suptitle('16. Тематическое моделирование борды (LDA)', fontsize=16, fontweight='bold', y=0.99, color="#ffffff")
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('16_lda_topics.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 16: {e}")

def _generate_chart_17(c, thirty_days_ago, images):
    """17. Индекс Токсичности (Сентимент)"""
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
                sns.lineplot(data=df_sent, x='d', y='sentiment', marker="o", color="#ff3333", ax=ax)
                ax.fill_between(df_sent['d'], df_sent['sentiment'], color="#ff3333", alpha=0.2)
                plt.title('17. Индекс Токсичности (Двачевский сентимент)', fontsize=16, fontweight='bold', color="#ff3333")
                plt.ylabel('Средний сентимент (выше = база, ниже = токсик)')
                plt.xticks(rotation=45)
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('17_sentiment.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 17: {e}")

def _generate_chart_18(c, thirty_days_ago, images):
    """18. Лексическое Разнообразие (MSTTR)"""
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
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('18_lexical_diversity.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 18: {e}")


def generate_all_charts():
    """Generates exactly 10 toxic charts and returns a list of io.BytesIO objects"""
    conn = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
    conn.row_factory = dict_factory
    c = conn.cursor()

    thirty_days_ago = time.time() - (30 * 24 * 3600)
    images = []
    _generate_chart_1(c, thirty_days_ago, images)
    _generate_chart_2(c, thirty_days_ago, images)
    _generate_chart_3(c, thirty_days_ago, images)
    _generate_chart_4(c, thirty_days_ago, images)
    _generate_chart_5(c, thirty_days_ago, images)
    _generate_chart_6(c, thirty_days_ago, images)
    _generate_chart_7(c, thirty_days_ago, images)
    _generate_chart_8(c, thirty_days_ago, images)
    _generate_chart_9(c, thirty_days_ago, images)
    _generate_chart_10(c, thirty_days_ago, images)
    _generate_chart_11(c, thirty_days_ago, images)
    _generate_chart_12(c, thirty_days_ago, images)
    _generate_chart_13(c, thirty_days_ago, images)
    _generate_chart_14(c, thirty_days_ago, images)
    _generate_chart_15(c, thirty_days_ago, images)
    _generate_chart_16(c, thirty_days_ago, images)
    _generate_chart_17(c, thirty_days_ago, images)
    _generate_chart_18(c, thirty_days_ago, images)
    conn.close()
    return images

if __name__ == "__main__":
    imgs = generate_all_charts()
    print(f"Generated {len(imgs)} toxic charts successfully.")
