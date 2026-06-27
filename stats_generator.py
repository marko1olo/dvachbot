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

def generate_all_charts():
    """Generates exactly 10 toxic charts and returns a list of io.BytesIO objects"""
    conn = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
    conn.row_factory = dict_factory
    c = conn.cursor()
    
    thirty_days_ago = time.time() - (30 * 24 * 3600)
    images = []
    
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
        sns.lineplot(data=df, x='d', y='cnt', marker="o", color="#ff3366", ax=ax)
        plt.title('1. Объем высеров (Посты по дням)', fontsize=16, fontweight='bold', color="#ff3366")
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('1_posts.png', buf))
        plt.close()
        
    # 2. Уникальные шизы (Weekly Active Users)
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

    # 3. Матоемкость борды
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
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('4_top_schizos.png', buf))
        plt.close()

    # 5. Главные Провокаторы (Топ-5 юзеров, кому больше всего отвечают)
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
        ax.set_xlim(0, df['cnt'].max() * 1.12)
        for idx, row in df.iterrows():
            ax.text(row['cnt'] + (ax.get_xlim()[1] * 0.01), idx, f"{int(row['cnt'])}", 
                    va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('5_provocateurs.png', buf))
        plt.close()

    # 6. Гистограмма длины постов (Одноклеточные vs Пасты)
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

    # 7. Клуб Полуночников (Night vs Day)
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

    # 8. Медиа-зависимость (Картинкодрочеры vs Текстовики)
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

    # 9. Уровень дискуссии (Реплаи vs Крик в пустоту)
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
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        images.append(('10_heatmap.png', buf))
        plt.close()

    # 11. Граф Социального Пузыря (Echo Chambers)
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
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('12_pagerank.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 12: {e}")

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
                ax.set_xlim(0, df_mut['score'].max() * 1.12)
                for idx, row in df_mut.iterrows():
                    ax.text(row['score'] + (ax.get_xlim()[1] * 0.01), idx, f"{int(row['score'])}", 
                            va='center', ha='left', fontsize=10, fontweight='bold', color="#ffffff")
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('13_circlejerk.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 13: {e}")

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

    # 15. Мем-Радар: Взлетающие Тренды (Rising Keywords)
    try:
        now_ts = time.time()
        seven_days_ago = now_ts - (7 * 24 * 3600)
        fourteen_days_ago = now_ts - (14 * 24 * 3600)
        
        c.execute("SELECT content, author_id FROM Posts WHERE timestamp > ?", (seven_days_ago,))
        this_week_posts = c.fetchall()
        
        c.execute("SELECT content, author_id FROM Posts WHERE timestamp BETWEEN ? AND ?", (fourteen_days_ago, seven_days_ago))
        last_week_posts = c.fetchall()
        
        def clean_text_local(raw_content):
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
        radar_stop = RU_STOP.union({
            'prefixes', 'prefix', 'injections', 'injection', 'signatures', 'signature', 
            'info', 'entry', 'exit', 'take', 'profit', 'zone', 'price', 'reason', 
            'buy', 'sell', 'usdt', 'btc', 'eth', 'sol', 'xmr', 'ltc', 'trx', 'trc', 
            'trc20', 'ton', 'sim', 'pnl', 'gross', 'net', 'limit', 'stop', 'cringe', 'report'
        })

        def get_word_counts(posts_list):
            from collections import Counter
            counts = Counter()
            for row in posts_list:
                # 1. Skip system posts
                if row.get('author_id') in (0, 1163970492):
                    continue
                    
                text = clean_text_local(row['content'])
                
                # 2. Skip logs and reports structurally
                if text.count('|') >= 3:
                    continue
                if '[INFO]' in text or '[DEBUG]' in text or '[ERROR]' in text:
                    continue
                if 'ChatGPT Cringe Report' in text or 'нелепых и шаблонных фразах' in text:
                    continue
                    
                tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ]{4,}', text.lower())
                for t in tokens:
                    if t not in radar_stop:
                        counts[t] += 1
            return counts

        this_week_counts = get_word_counts(this_week_posts)
        last_week_counts = get_word_counts(last_week_posts)
        
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
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('15_autocorrelation.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 15: {e}")

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
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('16_top_words.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 16: {e}")

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
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                images.append(('18_lexical_diversity.png', buf))
                plt.close()
    except Exception as e:
        print(f"Error Chart 18: {e}")

    # 19. Популярность разделов (Посты по доскам)
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
            if len(df_board) > 6:
                top_boards = df_board.head(5).copy()
                others_cnt = df_board.iloc[5:]['cnt'].sum()
                others_row = pd.DataFrame([{'board_id': 'other', 'cnt': others_cnt}])
                df_board_plot = pd.concat([top_boards, others_row], ignore_index=True)
            else:
                df_board_plot = df_board
                
            fig, ax = plt.subplots(figsize=(8, 8))
            ax.pie(df_board_plot['cnt'], labels=df_board_plot['board_id'], autopct='%1.1f%%', startangle=140, 
                   colors=sns.color_palette("hls", len(df_board_plot)))
            plt.title('19. Популярность разделов (Посты по доскам)', fontsize=16, fontweight='bold', color="#ffffff")
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('19_boards.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 19: {e}")

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
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('20_lorenz.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 20: {e}")

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
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('21_heatmap_180.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 21: {e}")

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
                ax2.fill_between(hrs, 0, y_n, color=color, alpha=0.42)
                ax2.plot(hrs, y_n, color=color, linewidth=2, alpha=0.95)
                ax2.set_xlim(-0.5, 23.5)
                ax2.set_ylim(0, 0.48)
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
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('22_ridge_weekday.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 22: {e}")

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
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('23_activity_clock.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 23: {e}")

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
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            images.append(('24_calendar_180.png', buf))
            plt.close()
    except Exception as e:
        print(f"Error Chart 24: {e}")

    conn.close()
    return images

def generate_user_stats_card(user_id: int, board_id: str, username: str) -> tuple[io.BytesIO, str]:
    import sys
    import os
    from PIL import Image, ImageDraw, ImageFont
    
    conn = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
    c = conn.cursor()
    
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
    all_users = [r[0] for r in c.fetchall()]
    try:
        rank = all_users.index(user_id) + 1
    except ValueError:
        rank = len(all_users) + 1
        
    conn.close()
    
    schizo_name = generate_schizo_name(user_id)
    
    role_name = {
        'admin': 'Админ',
        'mod': 'Модератор',
        'janitor': 'Дворник',
        'user': 'Анон'
    }.get(role, 'Анон')
    
    # Slang comment based on rank and posts
    if posts_count == 0:
        slang_comment = "Ньюфаг детектед. Иди читай правила борды, анон."
    elif rank <= 3:
        slang_comment = "ОП-хуй и бог тредов! База сертифицирована, скуфы падают ниц."
    elif posts_count > 300:
        slang_comment = "Почетный Скуф борды. Запах подпиваса и базированных мыслей за версту."
    elif balance < 10:
        slang_comment = "Нищук детектед. Проиграл все коины в рулетку или забанен за сажу."
    else:
        slang_comment = "Обычный сыч. Бамп в тред, сажу в комменты."
        
    text_report = (
        f"☘️ <b>Статистика пользователя {schizo_name}</b> (/${board_id}/)\n\n"
        f"👤 <b>Статус:</b> {role_name} {f'({custom_prefix})' if custom_prefix else ''}\n"
        f"🏅 <b>Ранг борды:</b> #{rank} из {len(all_users)}\n"
        f"📝 <b>Написано постов:</b> {posts_count}\n"
        f"🎭 <b>Получено реакций:</b> +{rx_received}\n"
        f"⚡ <b>Поставлено реакций:</b> {rx_given}\n"
        f"💰 <b>Баланс:</b> {int(balance)} RUB\n"
        f"🔇 <b>Схвачено мутов:</b> {mutes_count}\n"
        f"🌀 <b>Кринж-фактор:</b> {lie_media}%\n\n"
        f"💬 <i>\"{slang_comment}\"</i>"
    )
    
    width, height = 800, 450
    img = Image.new('RGB', (width, height), color='#1d1f21')
    draw = ImageDraw.Draw(img)
    
    try:
        font_path = "font1.ttf" if os.path.exists("font1.ttf") else "arial.ttf"
        font_title = ImageFont.truetype(font_path, 28)
        font_subtitle = ImageFont.truetype(font_path, 20)
        font_body = ImageFont.truetype(font_path, 18)
        font_mono = ImageFont.truetype(font_path, 16)
    except Exception:
        font_title = font_subtitle = font_body = font_mono = ImageFont.load_default()
        
    draw.rectangle([15, 15, width-15, height-15], outline='#373b41', width=3)
    draw.rectangle([20, 20, width-20, height-20], outline='#282a2e', width=1)
    
    draw.text((40, 40), schizo_name, fill='#b58900', font=font_title)
    
    status_text = f"ID: {user_id}  |  Board: /{board_id}/  |  Role: {role.upper()}"
    draw.text((40, 80), status_text, fill='#8abeb7', font=font_subtitle)
    
    draw.line([40, 115, width-40, 115], fill='#373b41', width=2)
    
    stats = [
        ("Посты (Posts):", str(posts_count), '#c5c8c6'),
        ("Ранг (Board Rank):", f"#{rank} / {len(all_users)}", '#f0c674'),
        ("Получено реакций:", f"+{rx_received}", '#b58900'),
        ("Поставлено реакций:", str(rx_given), '#859900'),
        ("Баланс (Balance):", f"{int(balance)} RUB", '#8abeb7'),
        ("Количество мутов:", str(mutes_count), '#cc6666'),
        ("Кринж-эффект (Lie):", f"{lie_media}%", '#b294bb')
    ]
    
    y = 135
    for label, val, val_color in stats:
        draw.text((60, y), label, fill='#969896', font=font_body)
        draw.text((320, y), val, fill=val_color, font=font_body)
        y += 35
        
    draw.line([500, 135, 500, height-60], fill='#373b41', width=1)
    
    avatar_box = [540, 140, 740, 320]
    draw.rectangle(avatar_box, fill='#282a2e', outline='#373b41', width=2)
    
    draw.text((560, 190), "BOARD", fill='#859900', font=font_subtitle)
    draw.text((560, 220), "CERTIFIED", fill='#859900', font=font_subtitle)
    draw.text((560, 250), role.upper(), fill='#cc6666', font=font_subtitle)
    
    draw.line([520, 345, width-60, 345], fill='#373b41', width=1)
    draw.text((520, 360), f"\"{slang_comment}\"", fill='#969896', font=font_mono)
    
    buf = io.BytesIO()
    img.save(buf, format='png')
    buf.seek(0)
    return buf, text_report

if __name__ == "__main__":
    imgs = generate_all_charts()
    print(f"Generated {len(imgs)} toxic charts successfully.")
