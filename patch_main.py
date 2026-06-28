import re

with open('main.py', 'r') as f:
    content = f.read()

helper_functions = """
async def _get_user_messages_map_for_edit(post_num: int) -> dict:
    copies_info = await get_post_copies(post_num)
    user_messages_map = defaultdict(list)
    if copies_info:
        for uid, mid in copies_info:
            user_messages_map[uid].append(mid)
    async with storage_lock:
        ram_copies = post_to_messages.get(post_num, {})
        for uid, mid_or_list in ram_copies.items():
            if isinstance(mid_or_list, list):
                for m in mid_or_list:
                    if m not in user_messages_map[uid]:
                        user_messages_map[uid].append(m)
            else:
                if mid_or_list not in user_messages_map[uid]:
                    user_messages_map[uid].append(mid_or_list)
    return user_messages_map

async def _get_post_data_for_edit(post_num: int):
    post_data_copy = {}
    content_copy = {}
    reply_author_id = None
    board_id = None
    async with storage_lock:
        post_data = messages_storage.get(post_num)
        if not post_data:
            return None, None, None, None
        content_type = post_data.get('content', {}).get('type')
        can_be_edited = content_type in ['text', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'media_group']
        if not can_be_edited:
            return None, None, None, None
        post_data_copy = post_data.copy()
        content_copy = post_data.get('content', {}).copy()
        board_id = post_data.get('board_id')
        reply_to_post_num = content_copy.get('reply_to_post')
        if reply_to_post_num:
            reply_author_id = messages_storage.get(reply_to_post_num, {}).get('author_id')
    return post_data_copy, content_copy, reply_author_id, board_id

def _build_edit_keyboard(content_copy: dict, post_num: int):
    final_keyboard = None
    if content_copy.get('poll_data'):
        poll_options = content_copy.get('poll_data', {}).get('options', [])
        if poll_options:
            buttons = []
            for i, option_text in enumerate(poll_options):
                button_text = option_text[:60]
                buttons.append(
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"poll_vote_{post_num}_{i}"
                    )
                )
            final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in buttons])
    return final_keyboard

async def _build_user_specific_texts(user_messages_map: dict, content_copy: dict, post_data_copy: dict, board_id: str, reply_author_id: int):
    user_specific_texts = {}
    text_or_caption_base = content_copy.get('text') or content_copy.get('caption')
    text_with_you_links = text_or_caption_base
    if text_or_caption_base and ">>" in text_or_caption_base:
        mentioned_authors = {}
        mentions = RE_YOU_PATTERN.findall(text_or_caption_base)
        if mentions:
            async with storage_lock:
                for m_num_str in mentions:
                    try:
                        m_num = int(m_num_str)
                        if m_num in messages_storage:
                            mentioned_authors[m_num] = messages_storage[m_num].get("author_id")
                    except ValueError:
                        continue
        text_with_you_links = add_you_to_my_posts_fast(
            text_or_caption_base,
            post_data_copy.get('author_id'),
            mentioned_authors
        )
    b_data = board_data[board_id]
    users_settings = b_data.get('user_settings', {})
    for user_id in user_messages_map.keys():
        header_text = content_copy.get('header', '')
        u_set = users_settings.get(user_id, {'hide': set()})
        should_hide = False
        if u_set['hide']:
            raw_content_text = content_copy.get('text') or content_copy.get('caption') or ""
            check_text = (header_text + " " + raw_content_text).lower()
            if any(word in check_text for word in u_set['hide']):
                should_hide = True
        head = f"<i>{escape_html(header_text)}</i>"
        if user_id == reply_author_id:
            head = head.replace("Пост", "🔴 Пост").replace("Post", "🔴 Post")
        if should_hide:
            lang_local = 'en' if board_id == 'int' else 'ru'
            placeholder = "🛡 Message hidden" if lang_local == 'en' else "🛡 Сообщение скрыто"
            full_text = f"{head}\\n{placeholder}"
        else:
            current_text_or_caption = text_or_caption_base
            if user_id == post_data_copy.get('author_id'):
                current_text_or_caption = text_with_you_links
            content_for_user = content_copy.copy()
            if 'text' in content_for_user: content_for_user['text'] = current_text_or_caption
            elif 'caption' in content_for_user: content_for_user['caption'] = current_text_or_caption
            formatted_body = await _format_message_body(
                content=content_for_user, user_id_for_context=user_id,
                post_data=post_data_copy, reply_to_post_author_id=reply_author_id,
                quote_info=content_for_user.get('quote_info')
            )
            full_text = f"{head}\\n\\n{formatted_body}" if formatted_body else head
        user_specific_texts[user_id] = full_text
    return user_specific_texts

"""

# find edit_post_for_all_recipients and insert helper functions right before it
import re

match = re.search(r'async def edit_post_for_all_recipients', content)
if match:
    insert_pos = match.start()
    new_content = content[:insert_pos] + helper_functions + content[insert_pos:]
    with open('main.py', 'w') as f:
        f.write(new_content)
