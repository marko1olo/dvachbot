import asyncio
import os
import json
import traceback
from typing import Dict, Any
from collections import defaultdict
from common.config import DATA_DIR
from shared_state import THREAD_BOARDS, storage_lock

# --- Private State ---
# _threads_data maps: board_id -> thread_id -> thread_info
_threads_data: Dict[str, Dict[str, Any]] = defaultdict(dict)
# _thread_locks maps: board_id -> thread_id -> asyncio.Lock
_thread_locks: Dict[str, Dict[str, asyncio.Lock]] = defaultdict(lambda: defaultdict(asyncio.Lock))

def initialize_board_threads(board_id: str, data: dict):
    """Initializes the threads data for a board from a loaded dict."""
    _threads_data[board_id] = data

def get_threads_data(board_id: str) -> dict:
    """Returns all threads data for a specific board."""
    return _threads_data[board_id]

def get_thread_info(board_id: str, thread_id: str) -> dict:
    """Returns specific thread info dict, or an empty dict if not found."""
    return _threads_data[board_id].get(str(thread_id), {})

def set_thread_info(board_id: str, thread_id: str, info: dict):
    """Sets the info dictionary for a specific thread."""
    _threads_data[board_id][str(thread_id)] = info

def delete_thread_data(board_id: str, thread_id: str):
    """Removes a thread and its lock from memory."""
    _threads_data[board_id].pop(str(thread_id), None)
    _thread_locks[board_id].pop(str(thread_id), None)

def acquire_thread_lock(board_id: str, thread_id: str) -> asyncio.Lock:
    """Returns the asyncio.Lock for the specified thread."""
    return _thread_locks[board_id][str(thread_id)]

def get_thread_locks_count(board_id: str) -> int:
    return len(_thread_locks[board_id])

def get_active_threads(board_id: str) -> dict:
    """Returns all non-archived threads for a board."""
    return {k: v for k, v in _threads_data[board_id].items() if not v.get('is_archived')}

def trim_thread_posts(board_id: str, thread_id: str, max_posts: int) -> list:
    """
    Trims the post list of a thread to max_posts, keeping the oldest first post 
    (OP post) and the newest (max_posts - 1) posts.
    Returns a list of post_nums that were trimmed (removed).
    """
    info = get_thread_info(board_id, thread_id)
    posts = info.get('posts', [])
    if len(posts) <= max_posts or not posts:
        return []
    
    op_post = posts[0]
    kept_posts = posts[-(max_posts - 1):]
    new_posts = [op_post] + kept_posts
    
    trimmed = [p for p in posts if p not in new_posts]
    info['posts'] = new_posts
    return trimmed

def _sync_save_threads_data(board_id: str, data_to_save: dict):
    threads_file = os.path.join(DATA_DIR, f'{board_id}_threads.json')
    try:
        with open(threads_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f'⛔ [{board_id}] Ошибка в потоке сохранения _threads.json: {e}')
        return False

async def save_threads_data(board_id: str, save_executor):
    """
    Asynchronously saves the threads data to disk.
    Requires the global save_executor to be passed from main.
    """
    if board_id not in THREAD_BOARDS:
        return
    async with storage_lock:
        original_data = _threads_data[board_id]
        data_to_save = {}
        for thread_id, thread_info in original_data.items():
            serializable_info = thread_info.copy()
            if 'subscribers' in serializable_info and isinstance(serializable_info['subscribers'], set):
                serializable_info['subscribers'] = list(serializable_info['subscribers'])
            data_to_save[thread_id] = serializable_info
            
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(save_executor, _sync_save_threads_data, board_id, data_to_save)
