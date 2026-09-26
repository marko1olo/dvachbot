"""
Extractive and Heuristic Summarizer for Dvachbot.
Provides 100% reliable, zero-API fallback summarization for imageboard threads,
chats, and periodic digests when external LLMs fail or hit rate limits.
"""

import re
import html
import random
from collections import Counter
from common.text_utils import clean_html_tags, sanitize_html

WAHA_THOUGHTS = [
    "Неведение — величайшее благословение слабого разума.",
    "Каждый шаг без веры — шаг во тьму.",
    "Истинный воин не ищет славы, он ищет исполнения долга.",
    "Жалость к еретику — это предательство человечества.",
    "Не спрашивай, почему ты должен умереть, спрашивай, как тебе умереть за Терру.",
    "Смерть в бою — высочайшая награда для верного.",
    "Пусть ксенос плачет, а еретик сгорает в очищающем огне!",
    "Молитва очищает душу, а болтер очищает плоть.",
    "Император знает, Император видит, Император воздаст.",
    "Сомнение рождает ересь, ересь рождает возмездие."
]

BLAT_INTRO_VARIANTS = [
    "Вечер в хату, босота! Пока вы спали, Кибер-Смотрящий раскидал расклад по понятиям.",
    "Часик в радость, чифир в сладость! Держите свежий воровской прогон по нашей хате.",
    "Зенки протрите, фраера. Смотрящий разобрал ночные малявы и определил кто есть кто.",
    "Расклад по хате готов. Внимательно слушайте базар и мотайте на ус."
]

STOPWORDS_RU = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему",
    "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть",
    "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для",
    "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз",
    "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем",
    "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно",
    "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот",
    "через", "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три",
    "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть",
    "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между",
    "это", "блять", "нах", "нахуй", "похуй", "сука", "ебать", "лол", "кек", "хз", "очень",
    "просто", "вообще", "кстати", "типа", "вроде", "короче"
}


def _parse_dump_lines(text_dump: str) -> list[dict]:
    """Parse unstructured imageboard/chat dump into structured post objects."""
    posts = []
    lines = text_dump.strip().split("\n")
    
    current_author = "Анон"
    current_reply = None
    
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
            
        # Match standard bot line: Name (Ответ на #123): text or Name: text
        m = re.match(r"^([^:(]+?)(?:\s*\((?:Ответ на|reply to|>>)\s*#?(\d+)\))?\s*:\s*(.*)$", line, re.IGNORECASE)
        if m:
            current_author = m.group(1).strip()
            current_reply = m.group(2)
            content = m.group(3).strip()
        else:
            # Fallback for headerless text
            content = line
            
        clean_text = clean_html_tags(content).strip()
        # Filter out noisy placeholders and sticker tags
        clean_lower = clean_text.lower()
        if clean_lower in ('[sticker]', '[photo]', '[animation]', '[video]', '[document]', '[media_group]', '[voice]'):
            continue
        if len(clean_text) < 4:
            continue
            
        posts.append({
            "author": current_author or "Анон",
            "reply_to": current_reply,
            "text": clean_text,
            "raw": line
        })
        
    return posts


def _extract_key_topics(posts: list[dict], max_topics: int = 5) -> list[dict]:
    """Cluster posts and extract top topics based on term frequency and coherence."""
    word_freq = Counter()
    
    for p in posts:
        words = re.findall(r'[A-Za-zА-Яа-яЁё0-9_-]{3,}', p["text"].lower())
        for w in words:
            if w not in STOPWORDS_RU and not w.isdigit():
                word_freq[w] += 1

    common_keywords = [w for w, _ in word_freq.most_common(15)]
    
    topics = []
    used_posts = set()
    
    for kw in common_keywords:
        matching_posts = [
            p for i, p in enumerate(posts) 
            if i not in used_posts and kw in p["text"].lower()
        ]
        if matching_posts:
            # Best representative post
            best_post = max(matching_posts, key=lambda p: len(p["text"]))
            used_posts.add(posts.index(best_post))
            topics.append({
                "keyword": kw.capitalize(),
                "post": best_post,
                "count": len(matching_posts)
            })
            if len(topics) >= max_topics:
                break
                
    # If keyword clustering found few topics, take top distinct posts by substance
    if len(topics) < max_topics:
        sorted_by_len = sorted(
            [p for i, p in enumerate(posts) if i not in used_posts],
            key=lambda p: len(p["text"]),
            reverse=True
        )
        for p in sorted_by_len:
            clean_sub = re.sub(r'>>\d+', '', p["text"]).strip()
            if len(clean_sub) >= 20:
                topics.append({
                    "keyword": clean_sub[:25] + "...",
                    "post": p,
                    "count": 1
                })
            if len(topics) >= max_topics:
                break

    return topics


def generate_extractive_summary(
    text_dump: str,
    prompt: str = "",
    lang: str = "ru",
    paragraph_count: int = 4,
    board_id: str = "b",
    context_name: str = ""
) -> str:
    """
    Generate a rich, cohesive, styled summary directly from the text dump.
    Never fails, immune to rate limits, censorship, or upstream network failures.
    """
    posts = _parse_dump_lines(text_dump)
    if not posts:
        if lang == 'en':
            return "📝 <b>Board Summary:</b> No active discussion was recorded in this window."
        elif lang == 'jp':
            return "📝 <b>スレ要約:</b> この期間に目立った投稿はありませんでした。"
        return "☕️ <b>Сводка палаты:</b> За последнее время активных обсуждений зафиксировано не было."

    # Style detection from prompt
    prompt_lower = (prompt or "").lower()
    is_warhammer = any(k in prompt_lower for k in ("вархаммер", "ордо", "инквизиц", "омнисси", "адептус", "маллеус", "еретик"))
    is_blat = any(k in prompt_lower for k in ("воровск", "поняти", "хат", "смотрящ", "маляв", "прогон", "босот"))

    author_counts = Counter(p["author"] for p in posts)
    top_authors = [auth for auth, _ in author_counts.most_common(5)]
    
    # Best quotes
    non_trivial_posts = [p for p in posts if len(p["text"]) > 25 and not p["text"].startswith('/')]
    spicy_quotes = sorted(non_trivial_posts or posts, key=lambda p: len(p["text"]), reverse=True)
    highlight_quote = spicy_quotes[0] if spicy_quotes else posts[0]
    secondary_quote = spicy_quotes[1] if len(spicy_quotes) > 1 else None

    # Topics
    topics = _extract_key_topics(posts, max_topics=max(3, min(7, paragraph_count)))

    if is_warhammer:
        return _format_warhammer_summary(board_id, posts, topics, highlight_quote, secondary_quote, top_authors, paragraph_count)
    elif is_blat:
        return _format_blat_summary(board_id, posts, topics, highlight_quote, secondary_quote, author_counts, paragraph_count)
    elif lang == 'en':
        return _format_en_summary(board_id, posts, topics, highlight_quote, paragraph_count)
    elif lang == 'jp':
        return _format_jp_summary(board_id, posts, topics, highlight_quote, paragraph_count)
    else:
        return _format_classic_summary(board_id, posts, topics, highlight_quote, secondary_quote, author_counts, paragraph_count, context_name)


def _format_warhammer_summary(board_id: str, posts: list, topics: list, quote: dict, sec_quote: dict | None, top_authors: list, paragraph_count: int) -> str:
    paragraphs = []
    
    # 1. Header & Astro-vibe
    p1 = (
        f"⚙️ <b>СВЯЩЕННОЕ ВОКС-ДОСЬЕ СЕКТОРА /{board_id}/</b> ⚙️\n\n"
        f"Слуги Императора! Священный инквизиционный сервитор обработал астропатические перехваты сектора /{board_id}/. "
        f"Уровень варп-возмущений и ментальной скверны за контрольный интервал оценен как критический, "
        f"однако рубежи Терры удерживаются несокрушимой волей верных."
    )
    paragraphs.append(p1)

    # 2. Key nodes of heresy and debate
    p2 = "📜 <b>Вскрытые узлы ереси и инфо-активности:</b>\n"
    for i, t in enumerate(topics[:4], 1):
        clean_snippet = html.escape(re.sub(r'>>\d+', '', t["post"]["text"]).strip())
        if len(clean_snippet) > 130:
            clean_snippet = clean_snippet[:127] + "..."
        p2 += f"• <b>Узел #{i} [{html.escape(t['post']['author'])}]:</b> <i>«{clean_snippet}»</i>\n"
    paragraphs.append(p2.strip())

    # 3. Dossier on subjects
    suspects_lines = []
    for auth in top_authors[:3]:
        status = random.choice([
            "Класс Угрозы: Еретик-вольнодумец",
            "Статус: Верный гвардеец Империума",
            "Статус: Подозрение в псайкерской мутации",
            "Класс Угрозы: Сервитор-болтун"
        ])
        suspects_lines.append(f"• <b>{html.escape(auth)}</b> ({status}) — отмечен в основных протоколах дознания.")
    p3 = "🔰 <b>Досье подозреваемых и аколитов сектора:</b>\n" + "\n".join(suspects_lines)
    paragraphs.append(p3)

    # 4. Intercept quote
    q_author = html.escape(quote["author"])
    q_text = html.escape(re.sub(r'>>\d+', '', quote["text"]).strip())
    p4 = (
        f"🎙 <b>Главный вокс-перехват дня:</b>\n"
        f"<i>«{q_text[:240]}»</i>\n"
        f"— <code>{q_author}</code>"
    )
    paragraphs.append(p4)

    # 5. Thought of the day & Verdict
    thought = random.choice(WAHA_THOUGHTS)
    p5 = (
        f"📖 <b>Мысль Дня:</b> <i>«{thought}»</i>\n\n"
        f"📊 <b>Анализ вокс-эфира:</b> Проверено депеш: {len(posts)}. Очагов ереси локализовано: {len(topics)}.\n"
        f"⚡️ <b>Приговор Инквизиции:</b> Экстерминатус временно отложен. Личному составу продолжать несение службы!\n"
        f"<i>Хвала Омниссии и Бессмертному Повелителю Человечества!</i>"
    )
    paragraphs.append(p5)

    return "\n\n".join(paragraphs[:max(3, paragraph_count)])


def _format_blat_summary(board_id: str, posts: list, topics: list, quote: dict, sec_quote: dict | None, author_counts: Counter, paragraph_count: int) -> str:
    paragraphs = []
    
    # 1. Intro
    intro = random.choice(BLAT_INTRO_VARIANTS)
    p1 = f"♠️ <b>ВОРОВСКОЙ ПРОГОН ИЗ КИБЕР-ХАТЫ</b> ♠️\n\n{intro}"
    paragraphs.append(p1)

    # 2. Main chatter and moves
    p2 = "🔥 <b>О чем гудела хата и какие были терки:</b>\n"
    for i, t in enumerate(topics[:4], 1):
        clean_snippet = html.escape(re.sub(r'>>\d+', '', t["post"]["text"]).strip())
        if len(clean_snippet) > 130:
            clean_snippet = clean_snippet[:127] + "..."
        p2 += f"• <b>Замес #{i} ({html.escape(t['post']['author'])}):</b> <i>«{clean_snippet}»</i>\n"
    paragraphs.append(p2.strip())

    # 3. Crowd breakdown
    p3 = (
        f"👁 <b>Расклад по пассажирам:</b>\n"
        f"Всего в хате сегодня отметилось <b>{len(author_counts)}</b> душ, накидали суммарно <b>{len(posts)}</b> маляв. "
        f"Самые говорливые бродяги держали рамсы по понятиям, гнилых стукачей вовремя приструнили."
    )
    paragraphs.append(p3)

    # 4. Spiciest quote
    q_author = html.escape(quote["author"])
    q_text = html.escape(re.sub(r'>>\d+', '', quote["text"]).strip())
    p4 = (
        f"📌 <b>Малява дня из общака:</b>\n"
        f"<i>«{q_text[:240]}»</i>\n"
        f"— <b>{q_author}</b>"
    )
    paragraphs.append(p4)

    # 5. Signet
    p5 = (
        f"♠️ <b>Вердикт Смотрящего:</b> Хата живет, общак полон, масть держится ровно.\n\n"
        f"<i>Жизнь ворам, хуй мусорам! АУЕ!</i>"
    )
    paragraphs.append(p5)

    return "\n\n".join(paragraphs[:max(3, paragraph_count)])


def _format_classic_summary(board_id: str, posts: list, topics: list, quote: dict, sec_quote: dict | None, author_counts: Counter, paragraph_count: int, context_name: str) -> str:
    paragraphs = []
    
    # 1. Header
    title = f"/{board_id}/" if not context_name else context_name
    p1 = (
        f"☕️ <b>АВТО-САММАРИ И СВОДКА ПАЛАТЫ ({title})</b> ☕️\n\n"
        f"<i>Сводка ключевых обсуждений, холиваров и активности за прошедший интервал:</i>"
    )
    paragraphs.append(p1)

    # 2. Main topics
    p2 = "🔥 <b>Главные темы и горячие обсуждения:</b>\n"
    for i, t in enumerate(topics[:5], 1):
        clean_snippet = html.escape(re.sub(r'>>\d+', '', t["post"]["text"]).strip())
        if len(clean_snippet) > 140:
            clean_snippet = clean_snippet[:137] + "..."
        p2 += f"• <b>{html.escape(t['post']['author'])}:</b> <i>«{clean_snippet}»</i>\n"
    paragraphs.append(p2.strip())

    # 3. Secondary topics / quotes if long summary requested
    if paragraph_count >= 4 and sec_quote:
        sq_auth = html.escape(sec_quote["author"])
        sq_text = html.escape(re.sub(r'>>\d+', '', sec_quote["text"]).strip())
        p3 = (
            f"💡 <b>Заметная мысль из тредов:</b>\n"
            f"<i>«{sq_text[:200]}»</i> — <b>{sq_auth}</b>"
        )
        paragraphs.append(p3)

    # 4. Quote of the day
    q_author = html.escape(quote["author"])
    q_text = html.escape(re.sub(r'>>\d+', '', quote["text"]).strip())
    p4 = (
        f"💬 <b>Цитата палаты:</b>\n"
        f"<i>«{q_text[:250]}»</i>\n"
        f"— <b>{q_author}</b>"
    )
    paragraphs.append(p4)

    # 5. Stats
    p5 = (
        f"📊 <b>Статистика движухи:</b> обработано сообщений: <b>{len(posts)}</b>, уникальных анонов: <b>{len(author_counts)}</b>.\n"
        f"🚀 <i>Деградация продолжается в штатном режиме!</i>"
    )
    paragraphs.append(p5)

    return "\n\n".join(paragraphs[:max(3, paragraph_count)])


def _format_en_summary(board_id: str, posts: list, topics: list, quote: dict, paragraph_count: int) -> str:
    paragraphs = []
    paragraphs.append(
        f"📝 <b>BOARD DIGEST (/{board_id}/)</b>\n\n"
        f"<i>A breakdown of recent discussions, bantz, and highlights:</i>"
    )
    
    p2 = "🔥 <b>Key Discussions:</b>\n"
    for i, t in enumerate(topics[:4], 1):
        clean_snippet = html.escape(re.sub(r'>>\d+', '', t["post"]["text"]).strip())
        if len(clean_snippet) > 130:
            clean_snippet = clean_snippet[:127] + "..."
        p2 += f"• <b>{html.escape(t['post']['author'])}:</b> <i>\"{clean_snippet}\"</i>\n"
    paragraphs.append(p2.strip())

    q_author = html.escape(quote["author"])
    q_text = html.escape(re.sub(r'>>\d+', '', quote["text"]).strip())
    paragraphs.append(
        f"💬 <b>Highlight of the Session:</b>\n"
        f"<i>\"{q_text[:220]}\"</i> — <b>{q_author}</b>"
    )

    paragraphs.append(
        f"📊 <b>Activity Stats:</b> Analyzed <b>{len(posts)}</b> posts. Status: Chaotic neutral."
    )
    return "\n\n".join(paragraphs[:max(3, paragraph_count)])


def _format_jp_summary(board_id: str, posts: list, topics: list, quote: dict, paragraph_count: int) -> str:
    paragraphs = []
    paragraphs.append(
        f"📝 <b>スレダイジェスト (/{board_id}/)</b>\n\n"
        f"<i>最近の話題と注目のレスまとめ:</i>"
    )
    
    p2 = "🔥 <b>主な話題:</b>\n"
    for i, t in enumerate(topics[:4], 1):
        clean_snippet = html.escape(re.sub(r'>>\d+', '', t["post"]["text"]).strip())
        if len(clean_snippet) > 100:
            clean_snippet = clean_snippet[:97] + "..."
        p2 += f"• <b>{html.escape(t['post']['author'])}:</b> <i>「{clean_snippet}」</i>\n"
    paragraphs.append(p2.strip())

    q_author = html.escape(quote["author"])
    q_text = html.escape(re.sub(r'>>\d+', '', quote["text"]).strip())
    paragraphs.append(
        f"💬 <b>注目のレス:</b>\n"
        f"<i>「{q_text[:180]}」</i> — <b>{q_author}</b>"
    )

    paragraphs.append(
        f"📊 <b>統計:</b> 合計 <b>{len(posts)}</b> レス解析済み。"
    )
    return "\n\n".join(paragraphs[:max(3, paragraph_count)])
