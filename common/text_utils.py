import re
import html
import json
from common.html_utils import escape_html

RE_HTML_TAGS = re.compile(r'<[^>]+>')
RE_YOU_PATTERN = re.compile(r">>(\d+)")
RE_SCRIPT_TAG = re.compile(r'<\s*script\b[^>]*>.*?<\s*/\s*script\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_SCRIPT_SINGLE = re.compile(r'<\s*script\b[^>]*>', flags=re.IGNORECASE)
RE_DANGEROUS_TAGS = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>.*?<\s*/\s*\1\s*>', flags=re.IGNORECASE | re.DOTALL)
RE_DANGEROUS_SINGLE = re.compile(r'<\s*(iframe|svg|form|object|embed|link)\b[^>]*>', flags=re.IGNORECASE)
# Ловит и закавыченные, и голые значения: on*=alert(1) без кавычек прежний
# паттерн (требовавший ["']) пропускал целиком.
RE_EVENT_HANDLERS = re.compile(
    r'''\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''',
    flags=re.IGNORECASE,
)
# style Telegram не поддерживает ни на одном теге, а в вебе это вектор
# для оверлеев поверх страницы.
RE_STYLE_ATTR = re.compile(
    r'''\s+style\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)''',
    flags=re.IGNORECASE,
)


def strip_unsafe_attributes(tag: str) -> str:
    """
    Вычищает обработчики событий и style из уже разрешённого тега.

    ALLOWED_TAGS_PATTERN пропускает разрешённые теги ДОСЛОВНО вместе с любыми
    атрибутами (`[^>]*`), поэтому <b onclick="..."> проходил санитайзер целиком.
    RE_EVENT_HANDLERS для этого и объявлялся, но нигде не применялся.

    Не трогаем остальные атрибуты: href, emoji-id, class="language-..." и
    expandable — легальные в Telegram HTML.
    """
    cleaned = RE_EVENT_HANDLERS.sub('', tag)
    return RE_STYLE_ATTR.sub('', cleaned)

RE_TG_EMOJI_FULL = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', flags=re.IGNORECASE | re.DOTALL)
RE_TG_EMOJI_STRIP = re.compile(r'</?tg-emoji\b[^>]*>', flags=re.IGNORECASE)

def unwrap_tg_emoji(text: str) -> str:
    if not text: return text
    text = RE_TG_EMOJI_FULL.sub(r'\1', text)
    text = RE_TG_EMOJI_STRIP.sub('', text)
    return text

ALLOWED_TAGS_PATTERN = re.compile(
    r'</?(?:b|i|u|s|code|pre|blockquote|tg-spoiler|tg-emoji|em|strong)\b[^>]*>|'
    r'<\s*a\s+[^>]*href=["\'](?:https?://|tg://)[^"\']+["\'][^>]*>|'
    r'</\s*a\s*>',
    flags=re.IGNORECASE
)

def clean_html_tags(text: str) -> str:
    if not text: return text
    text = unwrap_tg_emoji(text)
    return RE_HTML_TAGS.sub('', text)

RE_ATTRS = re.compile(
    r'''\b([a-z0-9_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',
    flags=re.IGNORECASE,
)

def sanitize_html(text: str) -> str:
    if not text: return ""

    text = unwrap_tg_emoji(text)

    parts = []
    last_idx = 0
    open_a_count = 0
    for match in ALLOWED_TAGS_PATTERN.finditer(text):
        start, end = match.span()
        tag_text = match.group(0)
        tag_lower = tag_text.lower()
        
        valid_a_tag = None
        if tag_lower.startswith('<a'):
            for attr_m in RE_ATTRS.finditer(tag_text):
                attr_name = attr_m.group(1).lower()
                if attr_name == "href":
                    val = attr_m.group(2) if attr_m.group(2) is not None else (attr_m.group(3) if attr_m.group(3) is not None else attr_m.group(4))
                    if val and val.lower().strip().startswith(("http://", "https://", "tg://")):
                        safe_val = html.escape(val, quote=True)
                        valid_a_tag = f'<a href="{safe_val}">'
                    break

        if start > last_idx:
            chunk = text[last_idx:start]
            chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(chunk_escaped)
        
        if tag_lower.startswith('<a'):
            if valid_a_tag:
                open_a_count += 1
                parts.append(valid_a_tag)
            else:
                parts.append(tag_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        elif tag_lower.startswith('</a'):
            if open_a_count > 0:
                open_a_count -= 1
                parts.append('</a>')
            else:
                parts.append(tag_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        else:
            parts.append(strip_unsafe_attributes(tag_text))
        last_idx = end
        
    if last_idx < len(text):
        chunk = text[last_idx:]
        chunk_escaped = chunk.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        parts.append(chunk_escaped)

    result = "".join(parts)
    result = re.sub(r'&amp;(lt|gt|amp|quot|#\d+);', r'&\1;', result)
    return result

def clean_html_for_tg(text: str) -> str:
    if not text: return ''

    # Defensive unwrap if model accidentally output raw JSON
    trimmed = text.strip()
    if trimmed.startswith("{") and trimmed.endswith("}"):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                extracted = (
                    data.get("text")
                    or data.get("summary")
                    or data.get("response")
                    or data.get("content")
                    or data.get("roast")
                    or data.get("verdict")
                )
                if extracted and isinstance(extracted, str):
                    text = extracted
        except Exception:
            pass

    # First unwrap custom Telegram emoji tags <tg-emoji emoji-id="...">EMOJI</tg-emoji> -> EMOJI
    text = unwrap_tg_emoji(text)

    # Markdown -> HTML
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Convert layout/semantic tags to whitespace BEFORE stripping
    # <p>, <br>, <h1-6>, <li>, <div> etc -> newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p\s*[^>]*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<hr\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?h[1-6]\s*[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:li|dt|dd|tr|td|th)\s*[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:div|section|article|header|footer|main|nav|aside|span|em|strong|ul|ol|table|thead|tbody|tfoot|figure|figcaption)\s*[^>]*>', '', text, flags=re.IGNORECASE)

    # Strip ALL remaining non-allowed tags completely
    allowed = {'b', 'i', 'u', 's', 'code', 'pre', 'a', 'tg-spoiler', 'tg-emoji', 'blockquote'}

    def _replace_tag(m):
        closing = m.group(1)  # '/' or None
        tag = m.group(2).lower()
        attrs = m.group(3)
        if tag in allowed:
            if closing:
                return f'</{tag}>'
            return f'<{tag}{attrs}>'
        return ''  # strip completely

    text = re.sub(r'<(/?)([a-zA-Z][a-zA-Z0-9_-]*)([^>]*)>', _replace_tag, text)

    # Collapse 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Balance remaining allowed tags
    parts = re.split(r'(</?[a-zA-Z0-9_-]+\b[^>]*>)', text)
    stack = []
    out = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            m = re.match(r'<(/)?([a-zA-Z]+)\b([^>]*)>', part)
            if m:
                is_closing = bool(m.group(1))
                tag_name = m.group(2).lower()
                attrs = m.group(3)
                if tag_name in allowed:
                    if not is_closing:
                        stack.append(tag_name)
                        out.append(part)
                    else:
                        if stack and stack[-1] == tag_name:
                            stack.pop()
                            out.append(part)
                        elif tag_name in stack:
                            while stack and stack[-1] != tag_name:
                                out.append(f'</{stack.pop()}>')
                            stack.pop()
                            out.append(part)
                        # else: orphan closing tag, skip
                # else: non-allowed, skip
            # else: malformed tag, skip
        else:
            out.append(part)
    while stack:
        out.append(f'</{stack.pop()}>')

    return "".join(out).strip()



def generate_poll_text_display(poll_data: dict) -> str:
    """
    Генерирует текстовое представление опроса с ASCII-барами.
    """
    if not poll_data or 'question' not in poll_data or 'options' not in poll_data:
        return ""
    question = escape_html(poll_data['question'])
    options = poll_data.get('options', [])
    votes = poll_data.get('votes', {})
    total_votes = sum(len(v) for v in votes.values())
    lines = [f"📊 <b>{question.upper()}</b>\n"]
    BAR_LENGTH = 14
    for i, option_text in enumerate(options):
        option_key = str(i)
        vote_count = len(votes.get(option_key, []))
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
        filled_length = int(BAR_LENGTH * vote_count / total_votes) if total_votes > 0 else 0
        bar = '█' * filled_length + '─' * (BAR_LENGTH - filled_length)
        safe_option_text = escape_html(option_text)
        lines.append(f"<code>{i+1}. {safe_option_text}:</code>\n<code>[{bar}] {vote_count} ({percentage:.0f}%)</code>")
    return "\n".join(lines)


def _strip_raw_thinking_tags(text: str) -> str:
    """
    Rigorously strips all thinking, reasoning, thought, and reflection blocks,
    including closed tags, unclosed/truncated tags, HTML-escaped tags,
    and conversational reasoning preambles.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Closed reasoning/thinking tags (raw and HTML entity escaped)
    pattern_closed = r'<(?:think|reasoning|thought|reflection)\b[^>]*>.*?</(?:think|reasoning|thought|reflection)>'
    text = re.sub(pattern_closed, '', text, flags=re.DOTALL | re.IGNORECASE)

    pattern_escaped_closed = r'&lt;(?:think|reasoning|thought|reflection)\b[^&]*&gt;.*?&lt;/(?:think|reasoning|thought|reflection)&gt;'
    text = re.sub(pattern_escaped_closed, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Unclosed opening tags (from opening tag to end of string)
    pattern_unclosed = r'<(?:think|reasoning|thought|reflection)\b[^>]*>.*$'
    text = re.sub(pattern_unclosed, '', text, flags=re.DOTALL | re.IGNORECASE)

    pattern_escaped_unclosed = r'&lt;(?:think|reasoning|thought|reflection)\b[^&]*&gt;.*$'
    text = re.sub(pattern_escaped_unclosed, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 3. Orphaned closing tags
    text = re.sub(r'</(?:think|reasoning|thought|reflection)>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'&lt;/(?:think|reasoning|thought|reflection)&gt;', '', text, flags=re.IGNORECASE)

    # 4. Multi-line thinking blocks: 'Thinking Process:\n...\n\n'
    text = re.sub(r'(?is)^\s*(?:Thinking Process|Reasoning|Thoughts?):\s*\n.*?\n\n', '', text)

    # 5. Standard conversational preambles
    text = re.sub(r'(?i)^\s*(?:Here(?:\'s| is) (?:a |the )?(?:thinking process|reasoning|summary):?|Thinking Process:?|Thought:?|Reasoning:?|Assistant:)\s*', '', text)

    return text.strip()


RE_PLANNING_STEP = re.compile(
    r'^\s*(?:\d+[\.\)]|\*|\-|\#+)?\s*\**\s*(?:'
    r'Analyze(?:\s+the)?\s+User\s+Input|'
    r'Analysis(?:\s+of\s+(?:the\s+)?(?:User\s+Input|Prompt|Task|Input\s+Log))?|'
    r'Identify\s+(?:Key\s+)?Constraints(?:\s*&\s*Conflicts)?|'
    r'Key\s+Constraints(?:\s*&\s*Conflicts)?|'
    r'Deconstruct\s+Input(?:\s+Log)?(?:\s+for\s+Narrative)?|'
    r'Deconstruction\s+of\s+Input(?:\s+Log)?|'
    r'Role\s*:|'
    r'Persona\s*:|'
    r'Task\s*:|'
    r'Structure\s*:\s*(?:STRICTLY|Strictly|strictly)|'
    r'Format\s+Rules\s*:|'
    r'Content\s+Requirements\s*:|'
    r'Input\s+Data\s*:|'
    r'Tone\s*(?:&|and)\s*(?:Style|Persona)\s*:|'
    r'Narrative\s+Arc\s*:|Core\s+Conflict\s*:|'
    r'Determine\s+(?:Tone|Persona|Target|Audience|Style)|'
    r'Planning(?:\s+Phase)?\s*:|Step-by-step\s+Plan\s*:|Chain\s+of\s+Thought\s*:|Internal\s+Reasoning\s*:|'
    r'CoT(?:\s+Process)?\s*:|Reasoning\s+Process\s*:|'
    r'Drafting(?:\s+Process)?\s*:|Prompt\s+Analysis\s*:|Task\s+Understanding\s*:|'
    r'Step\s*\d+\s*:\s*(?:Analyze|Identify|Deconstruct|Determine|Plan|Draft|Review|Check)'
    r')\b',
    re.IGNORECASE
)

RE_PLANNING_SUBITEM = re.compile(
    r'^\s*[\*\-]?\s*(?:Role|Task|Structure|Content Requirements|Format Rules|Input Data|'
    r'Initial|Tone|Slang|Format|Content|Theme|Reactions|Interruption|Long text accusation|'
    r'Target|Constraints|Removing|Adjusting|Drafting|We need to|The user|I will|Note|Draft)\s*:',
    re.IGNORECASE
)

RE_TRANSITION = re.compile(
    r'^\s*(?:\d+[\.\)]|\*|\-|\#+)?\s*\**\s*(?:'
    r'Final\s+(?:Output|Response|Summary|Draft|Verdict|Answer|Roast)|'
    r'New\s+draft|Draft(?:\s*\d+)?|'
    r'Output|Response|Summary|Саммари|Итоговый\s+ответ|'
    r'Вот\s+(?:саммари|ответ|разбор|текст)|'
    r'Here(?:\'s|\s+is)\s+(?:the\s+)?(?:summary|response|output)'
    r')\s*:\s*\**',
    re.IGNORECASE
)

RE_COT_MARKERS = [
    # 1. 'Removing "..." to avoid ...' or 'Removing \'...\''
    re.compile(r'(?is)^\s*[\*\-]?\s*Removing\s+["\'][^"\']*["\'][^\n]*', re.MULTILINE),
    # 2. '* Let\'s ...' or 'Let\'s adjust / change / make ...'
    re.compile(r'(?im)^\s*[\*\-]?\s*Let\'?s\b[^\n]*', re.MULTILINE),
    # 3. '* *New draft:*', '**New draft:**', 'New draft:', '* Draft:', 'Draft 1:'
    re.compile(r'(?im)^\s*\*+\s*(?:New\s+draft|Draft(?:\s*\d+)?|Final\s+(?:draft|response|verdict|answer|roast))\s*:\s*\*+', re.MULTILINE),
    re.compile(r'(?im)^\s*(?:New\s+draft|Draft(?:\s*\d+)?|Final\s+(?:draft|response|verdict|answer|roast)|Roast\s+text)\s*:\s*', re.MULTILINE),
    # 4. 'Thought:', 'Thoughts:', 'Reasoning:', 'Thinking Process:'
    re.compile(r'(?im)^\s*\*?\s*(?:Thought|Thoughts|Reasoning|Thinking Process|Thinking|Notes?)\s*:\s*[^\n]*', re.MULTILINE),
    # 5. Standalone English meta-commentary bullets preceding Russian text
    re.compile(r'(?im)^\s*[\*\-]\s*(?:Removing|Adjusting|Drafting|Let\'s|We need to|The user|I will|Tone:|Target:|Note:|Draft:).*?$', re.MULTILINE),
]


def strip_cot_and_drafts(text: str) -> str:
    """
    Rigorously strips LLM Chain-of-Thought artifacts, meta-reasoning comments,
    un-tagged planning preambles (such as '1. Analyze User Input:', 'Role: ...',
    'Structure: STRICTLY ...', 'Identify Key Constraints & Conflicts:',
    'Deconstruct Input Log for Narrative:'), and draft revision headers from
    generated output before synthesis or posting, while preserving legitimate
    user-facing content.
    """
    if not text or not isinstance(text, str):
        return ""

    # Run base XML thinking tags removal first
    s = _strip_raw_thinking_tags(text)

    # Strip known CoT header regexes
    for pattern in RE_COT_MARKERS:
        s = pattern.sub('', s)

    has_any_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', s))
    lines = s.split('\n')
    cleaned_lines = []
    in_planning_block = False
    found_russian_body = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            if not in_planning_block and (found_russian_body or not has_any_cyrillic):
                cleaned_lines.append("")
            i += 1
            continue

        # Check for transition markers to actual user content (e.g. 'Final Response:', 'Вот саммари:')
        if RE_TRANSITION.match(stripped):
            in_planning_block = False
            remainder = RE_TRANSITION.sub('', stripped).strip()
            if remainder:
                cleaned_lines.append(remainder)
                if re.search(r'[а-яА-ЯёЁ]', remainder):
                    found_russian_body = True
            i += 1
            continue

        # Check for start of an un-tagged planning step
        if RE_PLANNING_STEP.match(stripped):
            in_planning_block = True
            i += 1
            continue

        if in_planning_block:
            # Any indented line or sub-bullet under an active planning header is part of planning
            if line.startswith((' ', '\t')) or stripped.startswith(("-", "*", "+", "•")):
                i += 1
                continue

            # Sub-item fields inside planning blocks (e.g. '- Role:', '- Structure:')
            if RE_PLANNING_SUBITEM.match(stripped):
                i += 1
                continue

            # Commentary lines without Cyrillic inside planning block
            has_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', stripped))
            if not has_cyrillic:
                i += 1
                continue

            # If an unindented line with Cyrillic is reached that does not match planning markers,
            # we have transitioned to legitimate user content!
            in_planning_block = False
            found_russian_body = True
            cleaned_lines.append(stripped)
            i += 1
            continue

        # Outside planning block: standard line processing
        has_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', stripped))
        if has_any_cyrillic and not found_russian_body:
            # Check for English meta reasoning before the first Russian sentence
            if not has_cyrillic and any(kw in stripped.lower() for kw in (
                "adjust", "removing", "let's", "draft", "thought", "verdict", "style", "tone", "roast", "review",
                "analyze", "constraint", "structure", "persona", "summary", "response"
            )):
                i += 1
                continue
            if has_cyrillic:
                found_russian_body = True
                cleaned_lines.append(stripped)
        else:
            cleaned_lines.append(stripped)
        i += 1

    result = '\n'.join(cleaned_lines).strip()
    return result


clean_ai_thinking = strip_cot_and_drafts
strip_thinking_tags = strip_cot_and_drafts


def safe_tg_caption(text: str, max_len: int = 1024) -> str:
    """
    Truncates text to ensure it strictly does not exceed Telegram's caption limit (default 1024 chars),
    preserving valid HTML tags when possible and balancing any open tags.
    """
    if not text:
        return ""
    if len(text) <= max_len:
        return text

    cut_len = max(0, max_len - 20)
    truncated = text[:cut_len]
    last_lt = truncated.rfind('<')
    last_gt = truncated.rfind('>')
    if last_lt > last_gt:
        truncated = truncated[:last_lt]

    res = clean_html_for_tg(truncated + "...")
    if len(res) > max_len:
        plain = clean_html_tags(text)
        plain_cut = max(0, max_len - 3)
        res = plain[:plain_cut] + "..."

    if len(res) > max_len:
        res = res[:max_len]

    return res

