import re
import html
from typing import Any, Optional
from common.html_utils import escape_html
from common.text_utils import sanitize_html, clean_html_tags

# Regex matching board post headers across all board modes and styles:
# e.g.:
# - 🟣 Пост №504200
# - Пост №504198
# - Пост #504198
# - Post No.504198
# - 🔴 <b>/b/</b> | Пост №501389
# - <i>🟣 Анонимный пользователь - 🔴 Пост №502710</i>
# - 🪗 БАЯН ×2\n🟣 Пост №504200
# - 💙💛 Пост №12/500 (OP)
# - ++ СИГНАЛ #504200 ++
# - ⚡ Донесение №504200
# - 🌸 投稿 504200 番
# - レス番 504200
RE_BOARD_POST_HEADER = re.compile(
    r'(?:'
    r'(?:[🪗\s]*БАЯН(?:\s*[×x*]\s*\d+)?[\s\n]*)?'
    r'(?:(?:<i>|<b>|<code>|<u>|<s>)\s*)*'
    r'(?:[🟣🔴🟢🔵🟡🟠⚪🏴🌈💩🤮🇺🇦🇷🇺💙💛🌸💥🇵🇱⚡📜🟩🦅🎅🖥️🌑🌒🌓🌔🌝🌙⭐💢☢️\s]|(?:Анонимный пользователь\s*[-—–]\s*)|(?:/[a-z0-9_-]+/\s*\|?\s*))*'
    r'(?:'
    r'Пост\s*[№#N]|'
    r'Post\s*(?:No\.?|[№#N])|'
    r'レス番\s*|'
    r'投稿\s*|'
    r'\+\+\s*СИГНАЛ\s*#|'
    r'Донесение\s*[№#]|'
    r'Депеша\s*[№#]|'
    r'Пакет\s*[№#]|'
    r'Freedom\s+Post\s*[№#]|'
    r'Подарок\s*[№#]|'
    r'Сообщение\s*#|'
    r'Казус\s*[№#]'
    r')\s*'
    r'(\d+(?:/\d+)?(?:\s*\([A-Za-z0-9_]+\))?(?:\s*番)?)'
    r'(?:\s*\+\+)?'
    r'(?:\s*(?:</i>|</b>|</code>|</u>|</s>))*'
    r')',
    re.IGNORECASE
)

# Regex to detect if text contains a standalone board post header line
RE_BOARD_POST_LINE = re.compile(
    r'(?:^[ \t]*|[ \t]*\n[ \t]*)'
    r'(?:[🪗\s]*БАЯН(?:\s*[×x*]\s*\d+)?[\s\n]*)?'
    r'(?:(?:<i>|<b>|<code>|<u>|<s>)\s*)*'
    r'(?:[🟣🔴🟢🔵🟡🟠⚪🏴🌈💩🤮🇺🇦🇷🇺💙💛🌸💥🇵🇱⚡📜🟩🦅🎅🖥️🌑🌒🌓🌔🌝🌙⭐💢☢️\s]|(?:Анонимный пользователь\s*[-—–]\s*)|(?:/[a-z0-9_-]+/\s*\|?\s*))*'
    r'(?:'
    r'Пост\s*[№#N]|'
    r'Post\s*(?:No\.?|[№#N])|'
    r'レス番\s*|'
    r'投稿\s*|'
    r'\+\+\s*СИГНАЛ\s*#|'
    r'Донесение\s*[№#]|'
    r'Депеша\s*[№#]|'
    r'Пакет\s*[№#]|'
    r'Freedom\s+Post\s*[№#]|'
    r'Подарок\s*[№#]|'
    r'Сообщение\s*#|'
    r'Казус\s*[№#]'
    r')\s*'
    r'(\d+(?:/\d+)?(?:\s*\([A-Za-z0-9_]+\))?(?:\s*番)?)',
    re.IGNORECASE | re.MULTILINE
)


def is_forward_message(message: Any) -> bool:
    """
    Determines if an incoming Telegram message is a forward.
    Supports Telegram Bot API 7.0+ (forward_origin) and legacy fields.
    """
    if message is None:
        return False
    if getattr(message, 'forward_origin', None) is not None:
        return True
    if getattr(message, 'forward_from', None) is not None:
        return True
    if getattr(message, 'forward_from_chat', None) is not None:
        return True
    if getattr(message, 'forward_sender_name', None) is not None:
        return True
    if getattr(message, 'forward_date', None) is not None:
        return True
    return False


def is_forwarded_from_bot(message: Any, bot_instance: Any = None) -> bool:
    """
    Determines if an incoming Telegram message was forwarded from a bot (the board bot,
    an archive channel, or another bot).
    """
    if not is_forward_message(message):
        return False

    bot_id = None
    if bot_instance:
        bot_id = getattr(bot_instance, 'id', None)
    elif getattr(message, 'bot', None):
        bot_id = getattr(message.bot, 'id', None)

    # 1. forward_origin (aiogram 3 / Bot API 7.0+)
    origin = getattr(message, 'forward_origin', None)
    if origin:
        sender_user = getattr(origin, 'sender_user', None)
        if sender_user:
            if getattr(sender_user, 'is_bot', False):
                return True
            if bot_id and sender_user.id == bot_id:
                return True
            try:
                import shared_state
                if sender_user.id in getattr(shared_state, 'GLOBAL_BOTS', {}):
                    return True
                if hasattr(shared_state, 'BOT_ID') and sender_user.id == shared_state.BOT_ID:
                    return True
            except Exception:
                pass
            username = getattr(sender_user, 'username', '') or ''
            if username.lower().endswith('bot'):
                return True

        sender_chat = getattr(origin, 'sender_chat', None) or getattr(origin, 'chat', None)
        if sender_chat:
            try:
                import shared_state
                if hasattr(shared_state, 'ARCHIVE_CHANNEL_ID') and sender_chat.id == shared_state.ARCHIVE_CHANNEL_ID:
                    return True
            except Exception:
                pass

    # 2. legacy forward_from
    ff = getattr(message, 'forward_from', None)
    if ff:
        if getattr(ff, 'is_bot', False):
            return True
        if bot_id and ff.id == bot_id:
            return True
        try:
            import shared_state
            if ff.id in getattr(shared_state, 'GLOBAL_BOTS', {}):
                return True
            if hasattr(shared_state, 'BOT_ID') and ff.id == shared_state.BOT_ID:
                return True
        except Exception:
            pass
        username = getattr(ff, 'username', '') or ''
        if username.lower().endswith('bot'):
            return True

    # 3. legacy forward_from_chat
    fc = getattr(message, 'forward_from_chat', None)
    if fc:
        try:
            import shared_state
            if hasattr(shared_state, 'ARCHIVE_CHANNEL_ID') and fc.id == shared_state.ARCHIVE_CHANNEL_ID:
                return True
        except Exception:
            pass

    return False


def contains_board_post_header(text: str) -> bool:
    """
    Checks whether text contains a board post header (e.g. '🟣 Пост №504200' or 'Post No.12345').
    """
    if not text or not isinstance(text, str):
        return False
    return bool(RE_BOARD_POST_HEADER.search(text))


def extract_board_post_number(text: str) -> int | None:
    """
    Extracts the integer post number from the first board post header found in text.
    """
    if not text or not isinstance(text, str):
        return None
    match = RE_BOARD_POST_HEADER.search(text)
    if not match:
        return None
    raw_num = match.group(1)
    if not raw_num:
        return None
    # If thread format "12/500", take first number
    digits = re.match(r'^(\d+)', raw_num.strip())
    if digits:
        try:
            return int(digits.group(1))
        except ValueError:
            return None
    return None


def _clean_nested_blockquotes(text: str) -> str:
    """
    Replaces existing blockquotes inside text to prevent invalid nested blockquotes in Telegram HTML.
    Converts <blockquote>inner</blockquote> to <i>«inner»</i>.
    """
    if not text:
        return ""
    # Replace open tags
    text = re.sub(r'<blockquote\b[^>]*>', '<i>«', text, flags=re.IGNORECASE)
    # Replace close tags
    text = re.sub(r'</blockquote>', '»</i>', text, flags=re.IGNORECASE)
    return text


def format_forwarded_quote(text: str, is_forward: bool = False, expandable: bool | None = None) -> str:
    """
    Wraps forwarded text or quoted board posts into native Telegram <blockquote>...</blockquote>.
    
    - If text is already wrapped in <blockquote>...</blockquote>, returns it safely without double-wrapping.
    - If is_forward is True, wraps the sanitized text in <blockquote>.
    - If text contains a board post header, extracts/wraps the board post portion in <blockquote>.
    - Preserves HTML formatting and ensures valid escaping.
    """
    if not text or not isinstance(text, str):
        return ""

    stripped = text.strip()
    if not stripped:
        return text

    # If the text is already entirely wrapped in <blockquote>...</blockquote>, do not double-wrap
    if re.match(r'^<blockquote\b[^>]*>.*</blockquote>$', stripped, flags=re.IGNORECASE | re.DOTALL):
        return text

    # Choose whether to use expandable blockquote based on content length/lines
    if expandable is None:
        line_count = stripped.count('\n') + 1
        expandable = (len(stripped) > 160 or line_count >= 4)

    tag_open = "<blockquote expandable>" if expandable else "<blockquote>"
    tag_close = "</blockquote>"

    # Case 1: Explicit forward message (or starts with board post header)
    if is_forward:
        clean_content = _clean_nested_blockquotes(stripped)
        return f"{tag_open}{clean_content}{tag_close}"

    # Case 2: Contains a board post header in text
    match = RE_BOARD_POST_HEADER.search(stripped)
    if match:
        start_idx = match.start()
        # If the header starts at the beginning (or only whitespace/emojis before it)
        prefix = stripped[:start_idx].rstrip()
        board_content = stripped[start_idx:].strip()

        clean_board_content = _clean_nested_blockquotes(board_content)

        if not prefix:
            return f"{tag_open}{clean_board_content}{tag_close}"
        else:
            return f"{prefix}\n\n{tag_open}{clean_board_content}{tag_close}"

    return text
