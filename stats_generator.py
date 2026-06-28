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

def save_chart(images: list, filename: str, bbox_inches=None):
    buf = io.BytesIO()
    if bbox_inches:
        plt.savefig(buf, format='png', bbox_inches=bbox_inches)
    else:
        plt.savefig(buf, format='png')
    buf.seek(0)
    images.append((filename, buf))
    plt.close()

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
        save_chart(images, '2_wau.png')

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
        xs3 = list(range(len(df)))
        ax.fill_between(xs3, df['toxic_percent'], color='#ff0000', alpha=0.25)
        ax.plot(xs3, df['toxic_percent'], marker='X', color='#ff0000', linewidth=2)
        step3 = max(1, len(df)//10)
        ax.set_xticks(xs3[::step3])
        ax.set_xticklabels(df['d'].tolist()[::step3], rotation=45, ha='right', fontsize=7)
        plt.title('3. Матоемкость (% постов с матами)', fontsize=16, fontweight='bold', color='#ff0000')
        plt.ylabel('% постов с матом')
        plt.tight_layout()
        save_chart(images, '3_toxicity.png')

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
            save_chart(images, '6_post_length.png')

    # 7+8+9. Три пирога в одном — Ночники / Медиа / Диалог
    c.execute('''
        SELECT 
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as night_posts,
            SUM(CASE WHEN cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) NOT BETWEEN 1 AND 6 THEN 1 ELSE 0 END) as day_posts,
            SUM(CASE WHEN content LIKE '%"type": "text"%' THEN 1 ELSE 0 END) as text_posts,
            SUM(CASE WHEN content LIKE '%"type": "photo"%' OR content LIKE '%"type": "video"%' OR content LIKE '%"type": "animation"%' THEN 1 ELSE 0 END) as media_posts,
            SUM(CASE WHEN reply_to_post_num IS NOT NULL THEN 1 ELSE 0 END) as replies,
            SUM(CASE WHEN reply_to_post_num IS NULL THEN 1 ELSE 0 END) as singles
        FROM Posts WHERE timestamp > ?
    ''', (thirty_days_ago,))
    row789 = c.fetchone()
    if row789:
        fig, axes = plt.subplots(1, 3, figsize=(16, 6))
        fig.patch.set_facecolor('#121212')
        _donuts = [
            {'ax': axes[0], 'sizes': [row789['night_posts'] or 0, row789['day_posts'] or 0],
             'labels': ['Ночь\n(01-06)', 'День'], 'colors': ['#6600cc', '#ffcc00'],
             'title': '7. Клуб\nПолуночников', 'tc': '#aa88ff'},
            {'ax': axes[1], 'sizes': [row789['media_posts'] or 0, row789['text_posts'] or 0],
             'labels': ['Медиа', 'Текст'], 'colors': ['#ff3399', '#cccccc'],
             'title': '8. Картинко-\nдрочеры', 'tc': '#ff3399'},
            {'ax': axes[2], 'sizes': [row789['replies'] or 0, row789['singles'] or 0],
             'labels': ['Диалог', 'Монолог'], 'colors': ['#00ff99', '#555555'],
             'title': '9. Уровень\nДискуссии', 'tc': '#00ff99'},
        ]
        for _d in _donuts:
            _ax = _d['ax']; _ax.set_facecolor('#121212')
            _ws, _ts, _ats = _ax.pie(
                _d['sizes'], labels=_d['labels'], autopct='%1.1f%%', startangle=90,
                colors=_d['colors'], wedgeprops=dict(width=0.55, edgecolor='#121212', linewidth=2),
                pctdistance=0.75)
            for _at in _ats: _at.set_fontsize(11); _at.set_fontweight('bold'); _at.set_color('#ffffff')
            for _t in _ts: _t.set_color('#dddddd'); _t.set_fontsize(9)
            _ax.set_title(_d['title'], fontsize=13, fontweight='bold', color=_d['tc'], pad=12)
        plt.suptitle('7–9. Профиль Анона: время / формат / диалог (30д)',
                     fontsize=14, fontweight='bold', color='#ffffff', y=1.02)
        plt.tight_layout()
        save_chart(images, '7_8_9_donut_panel.png', bbox_inches='tight')

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
                save_chart(images, '11_echo_chambers.png')
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
                save_chart(images, '12_pagerank.png')
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
                save_chart(images, '13_circlejerk.png')
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
                save_chart(images, '14_sessions.png')
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
            save_chart(images, '15_autocorrelation.png')
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
                save_chart(images, '16_top_words.png')
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
            save_chart(images, '19_boards.png')
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
            save_chart(images, '20_lorenz.png')
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
            save_chart(images, '21_heatmap_180.png')
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

    conn.close()

    # ── 25. Кумулятивный рост постов (всё время) ─────────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
        c2.execute('''
            SELECT date(timestamp, 'unixepoch', 'localtime') as d, COUNT(*) as cnt
            FROM Posts GROUP BY d ORDER BY d
        ''')
        data = c2.fetchall()
        conn2.close()
        if data:
            df = pd.DataFrame(data)
            df['cumsum'] = df['cnt'].cumsum()
            fig, ax = plt.subplots(figsize=(10, 4))
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

    # ── 26. Глубина цепочек ответов (30д) ────────────────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
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
        conn2.close()
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

    # ── 27. Радар здоровья борды ──────────────────────────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
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
        conn2.close()

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
        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_subplot(111, polar=True)
        ax.set_facecolor('#0d1117')
        ax.plot(angles, vals_r, color='#39d353', linewidth=2)
        ax.fill(angles, vals_r, color='#39d353', alpha=0.25)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=8.5, color='#e6edf3')
        ax.set_ylim(0, 1)
        ax.set_yticks([0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=6, color='#8b949e')
        ax.grid(color='#21262d', linewidth=0.7)
        ax.spines['polar'].set_color('#21262d')
        ax.set_title('27. Радар здоровья борды', fontsize=13, fontweight='bold',
                     color='#39d353', pad=18)
        plt.tight_layout()
        save_chart(images, '27_radar.png')
    except Exception as e:
        print(f"Error Chart 27: {e}")

    # ── 28. Топ тредов — пузырьковая диаграмма ───────────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
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
        conn2.close()
        if data and len(data) >= 3:
            posts   = [row['posts']   for row in data]
            authors = [row['authors'] for row in data]
            freshness = [(time.time() - row['last_ts']) / 3600 for row in data]  # hours ago
            labels  = [f"#{row['thread_id']}" for row in data]
            import numpy as _np3
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

    # ── 29. Тренд медиа vs текст по дням (30д) ─────────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
        t30_29 = time.time() - 30 * 86400
        c2.execute('''
            SELECT date(timestamp, 'unixepoch', 'localtime') as d,
                   SUM(CASE WHEN content LIKE '%"type": "text"%' THEN 1 ELSE 0 END) as txt,
                   SUM(CASE WHEN content LIKE '%"type": "photo"%' OR content LIKE '%"type": "video"%' OR content LIKE '%"type": "animation"%' OR content LIKE '%"type": "sticker"%' THEN 1 ELSE 0 END) as med
            FROM Posts WHERE timestamp > ? GROUP BY d ORDER BY d
        ''', (t30_29,))
        rows29 = c2.fetchall()
        conn2.close()
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

    # ── 30. Когорты новых авторов по неделям (13 нед) ─────────────────────────
    try:
        conn2 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        conn2.row_factory = dict_factory
        c2 = conn2.cursor()
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
        conn2.close()
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

    # ── 31. Активность борд по неделям (12 нед) stacked area ─────────────────
    try:
        _conn31 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        _conn31.row_factory = dict_factory
        _c31 = _conn31.cursor()
        _t84 = time.time() - 84 * 86400
        _c31.execute('''
            SELECT strftime('%Y-%W', datetime(timestamp, 'unixepoch', 'localtime')) as wk,
                   board_id, COUNT(*) as cnt
            FROM Posts WHERE timestamp > ? AND board_id IS NOT NULL
            GROUP BY wk, board_id ORDER BY wk
        ''', (_t84,))
        _rows31 = _c31.fetchall(); _conn31.close()
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

    # ── 32. Стрик-чемпионы (60д) Top-20, dual-column ─────────────────────────
    try:
        import datetime as _dt32
        from collections import defaultdict as _dd32
        _conn32 = sqlite3.connect('file:dvach_bot.db?mode=ro', uri=True)
        _conn32.row_factory = dict_factory
        _c32 = _conn32.cursor()
        _t60 = time.time() - 60 * 86400
        _c32.execute('''
            SELECT author_id, date(timestamp, 'unixepoch', 'localtime') as d
            FROM Posts
            WHERE timestamp > ? AND author_id IS NOT NULL AND author_id != 0
            GROUP BY author_id, d ORDER BY author_id, d
        ''', (_t60,))
        _rows32 = _c32.fetchall(); _conn32.close()
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
    draw.text((30, 22), schizo_name, fill='#ff9900', font=font_title)
    status_text = f"ID: {user_id}  |  Раздел: /{board_id}/  |  Статус: {role_name} {f'({custom_prefix})' if custom_prefix else ''}"
    draw.text((30, 60), status_text, fill='#8abeb7', font=font_subtitle)
    
    # Certified badge (top right)
    draw.rounded_rectangle([610, 15, 770, 80], radius=6, fill='#1b1f28', outline='#ff9900', width=2)
    draw.text((690, 33), "ТГАЧ CERTIFIED", fill='#ff9900', font=font_subtitle, anchor="mm")
    sub_cert = "APPROVED BITYARD" if role != 'admin' else "ADMINISTRATOR"
    draw.text((690, 58), sub_cert, fill='#00ffcc', font=ImageFont.truetype(font_path, 10) if os.path.exists(font_path) else font_subtitle, anchor="mm")
    
    # Helper to draw cards
    def draw_card(x, y, w, h, val, label, color):
        draw.rounded_rectangle([x, y, x+w, y+h], radius=6, fill='#13171f', outline='#252932', width=1)
        draw.ellipse([x+15, y+16, x+23, y+24], fill=color)
        draw.text((x+33, y+20), label, fill='#969896', font=font_card_lbl, anchor="lm")
        draw.text((x+15, y+48), val, fill=color, font=font_card_num, anchor="lm")

    # Cards grid
    cards = [
        (30, 115, 175, 80, str(posts_count), "Написано постов", "#00ffcc"),
        (220, 115, 175, 80, f"#{rank} / {len(all_users)}", "Ранг на борде", "#ffcc00"),
        (410, 115, 175, 80, f"{int(balance)} RUB", "Баланс коинов", "#00ff66"),
        
        (30, 210, 175, 80, f"+{rx_received}", "Получено реакций", "#ff3399"),
        (220, 210, 175, 80, str(rx_given), "Поставлено реакций", "#859900"),
        (410, 210, 175, 80, f"{lie_media}%", "Кринж-фактор", "#cc00ff"),
    ]
    
    for x, y, w, h, val, label, color in cards:
        draw_card(x, y, w, h, val, label, color)
        
    # Mutes Card (top right block)
    draw.rounded_rectangle([600, 115, 770, 175], radius=6, fill='#1d1315', outline='#ff3333', width=1)
    draw.ellipse([600+15, 115+16, 600+23, 115+24], fill="#ff3333")
    draw.text((600+33, 115+20), "Схвачено мутов", fill='#969896', font=font_card_lbl, anchor="lm")
    draw.text((600+15, 115+48), f"{mutes_count} шт", fill="#ff3339", font=font_card_num, anchor="lm")
    
    # Activity Level Card (below mutes)
    draw.rounded_rectangle([600, 210, 770, 290], radius=6, fill='#13171f', outline='#252932', width=1)
    draw.text((615, 230), "Уровень деградации", fill='#969896', font=font_card_lbl)
    activity_pct = min(1.0, posts_count / 500.0)
    draw.rounded_rectangle([615, 255, 755, 267], radius=3, fill='#1b1f28')
    draw.rounded_rectangle([615, 255, 615 + int(140 * activity_pct), 267], radius=3, fill='#ff9900')
    draw.text((755, 230), f"{int(activity_pct*100)}%", fill='#ff9900', font=font_card_lbl, anchor="ra")
    
    # Bottom Summary Box
    draw.rounded_rectangle([30, 310, 770, 420], radius=8, fill='#1b1f28', outline='#252932', width=1)
    draw.text((50, 335), "РЕЗЮМЕ ДЕГРАДАЦИИ:", fill='#ff9900', font=font_card_lbl)
    
    # Wrap comment safely
    import textwrap
    wrapped_lines = textwrap.wrap(f'"{slang_comment}"', width=90)
    y_comm = 360
    for line in wrapped_lines[:2]:
        draw.text((50, y_comm), line, fill='#e6edf3', font=font_comment)
        y_comm += 20
        
    buf = io.BytesIO()
    img.save(buf, format='png')
    buf.seek(0)
    return buf, text_report

if __name__ == "__main__":
    imgs = generate_all_charts()
    print(f"Generated {len(imgs)} toxic charts successfully.")
