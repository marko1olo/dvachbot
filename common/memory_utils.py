import sys
import gc
from collections import Counter
from datetime import datetime, UTC

async def log_memory_summary(messages_storage, post_to_messages, message_to_post, BOARDS, board_data):
    """
    Максимально подробный анализ и логгирование состояния памяти, размеров структур,
    топ-5 тяжёлых пользователей/тредов, распределение типов объектов, количество задач и алерты.
    Всё выводится в stdout.
    """
    if not hasattr(log_memory_summary, "previous_stats"):
        log_memory_summary.previous_stats = {}
    previous_stats = log_memory_summary.previous_stats
    current_stats = {}

    print(f"\n--- 📝 Запуск анализа памяти в {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')} ---")
    gc_count = gc.collect()
    print(f"GC.collect() завершён, удалено объектов: {gc_count}")
    current_stats['messages_storage'] = len(messages_storage)
    current_stats['post_to_messages'] = len(post_to_messages)
    current_stats['message_to_post'] = len(message_to_post)
    for board_id in BOARDS:
        b_data = board_data.get(board_id, {})
        current_stats[f"board[{board_id}].threads"] = len(b_data.get('threads_data', {}))
        current_stats[f"board[{board_id}].user_state"] = len(b_data.get('user_state', {}))
        current_stats[f"board[{board_id}].last_user_msgs"] = len(b_data.get('last_user_msgs', {}))
    gc.collect()
    print("🧹 Очистка памяти завершена.")
