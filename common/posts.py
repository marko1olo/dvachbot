import json
import time
from typing import List, Union
from urllib.parse import quote
import os
import hashlib

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("Необходимо установить SECRET_KEY в вашем .env файле.")

def get_user_hash(user_id: Union[int, str]) -> str:
    if not user_id: return "system"
    return hashlib.sha256((str(user_id) + SECRET_KEY).encode()).hexdigest()[:12]

def _normalize_post_id(post: dict) -> None:
    if 'post_num' in post:
        post['id'] = post.pop('post_num')

def _parse_post_content(post: dict) -> None:
    if isinstance(post.get('content'), str):
        try:
            post['content'] = json.loads(post['content'])
        except:
            post['content'] = {"text": str(post.get('content', '')), "type": "text"}
    if not isinstance(post.get('content'), dict):
        post['content'] = {"text": "", "type": "text"}

def _process_media_group(content: dict) -> None:
    file_list = []
    found_caption = None
    for item in content['media']:
        f_type = item.get('type')
        f_id = item.get('file_id') or item.get('media')
        if not found_caption and item.get('caption'):
            found_caption = item.get('caption')
        if f_id and isinstance(f_id, str) and not f_id.startswith("<"):
            clean_type = 'image' if f_type == 'photo' else f_type
            file_list.append({
                'type': clean_type,
                'original_file_id': f_id,
                'thumbnail_file_id': f_id,
                'filename': f"media_{f_id[:8]}.jpg" if clean_type == 'image' else f"media_{f_id[:8]}.mp4"
            })
    content['files'] = file_list
    if not content.get('text') and found_caption:
        content['text'] = found_caption

def _process_single_media(content: dict) -> None:
    file_info = {'type': content['type']}
    ctype = content['type']
    if ctype == 'photo' and content.get('photo') and isinstance(content['photo'], list):
        try:
            file_info['original_file_id'] = content['photo'][-1].get('file_id')
            file_info['thumbnail_file_id'] = content['photo'][0].get('file_id')
            file_info['type'] = 'image'
        except: pass
    else:
        f_obj = content.get(ctype) or content
        f_id = f_obj.get('file_id')
        thumb_source = f_obj.get('thumb') or f_obj.get('thumbnail')
        if thumb_source and isinstance(thumb_source, dict):
            file_info['thumbnail_file_id'] = thumb_source.get('file_id')
        mime = f_obj.get('mime_type', '')
        if ctype == 'document' and mime.startswith('video/'):
            file_info['type'] = 'video'
        if f_id:
            file_info['original_file_id'] = f_id
    if file_info.get('original_file_id'):
        content['files'] = [file_info]

def _process_files(content: dict) -> None:
    valid_files = []
    for file_info in content['files']:
        file_info.setdefault('dupe_count', 0)
        orig_url = file_info.get('original_url', '')
        if orig_url and 'local_file://' in orig_url:
            clean_id = orig_url.split('local_file://')[1]
            file_info['original_file_id'] = clean_id
            file_info['original_url'] = f"/files/{clean_id}"
        oid = file_info.get('original_file_id')
        if not oid or oid.startswith('<'):
            continue
        fname = file_info.get('filename', '').lower()
        if fname.endswith(('.mp4', '.webm', '.mov', '.mkv')) and file_info.get('type') not in ['voice', 'audio']:
            file_info['type'] = 'video'
        if fname.endswith('.webm') and file_info.get('type') == 'sticker':
            file_info['type'] = 'video'
        ftype = file_info.get('type', 'file')
        ext_map = {
            'video': 'mp4',
            'photo': 'jpg',
            'image': 'jpg',
            'audio': 'mp3',
            'voice': 'ogg',
            'sticker': 'webp',
            'video_note': 'mp4',
            'animation': 'mp4',
            'gif': 'mp4'
        }

        if not fname or fname.startswith('.') or fname == 'file' or '.' not in fname:
            ext = ext_map.get(ftype, 'dat')
            prefix = "vid" if ftype in ['video', 'animation', 'video_note', 'gif'] else ("aud" if ftype in ['audio', 'voice'] else "img")
            short_id = oid[:8] if oid else str(int(time.time()))
            file_info['filename'] = f"{prefix}_{short_id}.{ext}"
        elif '.' not in fname and ftype in ext_map:
            file_info['filename'] = f"{fname}.{ext_map[ftype]}"

        safe_name = quote(str(file_info.get('filename', 'file')).strip('/'))

        oid_str = str(oid) if oid else ""
        if oid_str.startswith(('http://', 'https://')):
            file_info['original_url'] = oid_str
        else:
            clean_oid = oid_str.strip('/')
            if clean_oid:
                file_info['original_url'] = f"/files/{clean_oid}/{safe_name}"
            else:
                file_info['original_url'] = f"/files/{safe_name}"

        tid = file_info.get('thumbnail_file_id')
        if tid:
            tid_str = str(tid)
            if tid_str.startswith(('http://', 'https://')):
                file_info['thumbnail_url'] = tid_str
            else:
                file_info['thumbnail_url'] = f"/files/{tid_str.strip('/')}"
        else:
            file_info['thumbnail_url'] = ""
        valid_files.append(file_info)
    content['files'] = valid_files

def _determine_post_type(content: dict) -> None:
    current_type = content.get('type')
    has_files = bool(content.get('files'))
    if current_type != 'poll':
        if has_files:
            content['type'] = 'files'
        else:
            content['type'] = 'text'

def _enrich_author_and_report_count(post: dict) -> None:
    post['report_count'] = post.get('report_count', 0)
    if 'author_id' in post:
        post['author_id'] = get_user_hash(post['author_id'])

def _convert_and_enrich_posts(posts: List[dict]) -> List[dict]:
    if not posts:
        return []
    for post in posts:
        if not post: continue

        _normalize_post_id(post)
        _parse_post_content(post)

        if post.get('latest_replies'):
            post['latest_replies'] = _convert_and_enrich_posts(post['latest_replies'])

        content = post['content']
        if content.get('type') == 'media_group' and 'media' in content:
            _process_media_group(content)
        elif content.get('type') in {'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker', 'video_note'} and 'files' not in content:
            _process_single_media(content)

        if 'files' in content and isinstance(content['files'], list):
            _process_files(content)

        _determine_post_type(content)
        _enrich_author_and_report_count(post)

    return posts
