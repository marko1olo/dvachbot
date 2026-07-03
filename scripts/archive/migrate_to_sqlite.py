import asyncio
import json
import glob
import gzip
import os
from datetime import datetime, UTC

import aiosqlite

# Импортируем необходимые компоненты из наших модулей
from database import DB_NAME, initialize_database
from main import BOARD_CONFIG, BOARDS, THREAD_BOARDS, DATA_DIR


def _read_json_file(path: str):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


def _read_gzip_json_file(path: str):
    with gzip.open(path, "rt", encoding="utf-8") as file:
        return json.load(file)


async def migrate():
    """
    Основная функция для миграции данных из JSON-файлов в SQLite.
    """
    print("--- НАЧАЛО МИГРАЦИИ ДАННЫХ ---")
    
    # Убедимся, что база данных и таблицы существуют
    await initialize_database()

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Миграция Досок (Boards)
        print("\n[1/5] Миграция досок...")
        boards_data = []
        for board_id, config in BOARD_CONFIG.items():
            desc = config.get('description', '')
            if isinstance(desc, dict):
                desc = json.dumps(desc, ensure_ascii=False)
            boards_data.append((board_id, config.get('name', ''), desc))

        await db.executemany(
            "INSERT OR REPLACE INTO Boards (board_id, name, description) VALUES (?, ?, ?)",
            boards_data
        )
        await db.commit()
        print(f"  > Готово. Мигрировано {len(BOARD_CONFIG)} досок.")

        # 2. Миграция Пользователей и Мутов (Users & Mutes)
        print("\n[2/5] Миграция пользователей и мутов...")
        total_users = 0
        total_mutes = 0
        active_users_data = []
        banned_users_data = []
        mutes_data = []
        for board_id in BOARDS:
            state_file = f"{board_id}_state.json"
            if not os.path.exists(state_file):
                continue

            data = await asyncio.to_thread(_read_json_file, state_file)
            
            # Пользователи
            active_users = data.get('users_data', {}).get('active', [])
            banned_users = data.get('users_data', {}).get('banned', [])
            
            active_users_data.extend([(user_id, board_id, 'active') for user_id in active_users])
            total_users += len(active_users)

            banned_users_data.extend([(user_id, board_id, 'banned') for user_id in banned_users])
            total_users += len(banned_users)

            # Муты (только shadow_mutes, так как обычные не сохраняются)
            shadow_mutes = data.get('shadow_mutes', {})
            for user_id_str, expiry_str in shadow_mutes.items():
                try:
                    user_id = int(user_id_str)
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    if expiry_dt > datetime.now(UTC):
                        mutes_data.append((user_id, board_id, 'shadow', expiry_dt.timestamp()))
                        total_mutes += 1
                except (ValueError, TypeError):
                    continue

        if active_users_data:
            await db.executemany(
                "INSERT OR IGNORE INTO Users (user_id, board_id, status) VALUES (?, ?, ?)",
                active_users_data
            )
        if banned_users_data:
            await db.executemany(
                "INSERT OR REPLACE INTO Users (user_id, board_id, status) VALUES (?, ?, ?)",
                banned_users_data
            )
        if mutes_data:
            await db.executemany(
                """
                INSERT OR REPLACE INTO Mutes (user_id, board_id, mute_type, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                mutes_data
            )
        await db.commit()
        print(f"  > Готово. Мигрировано {total_users} записей о пользователях и {total_mutes} мутов.")

        # 3. Миграция Тредов (Threads)
        print("\n[3/5] Миграция тредов и состояний пользователей в тредах...")
        total_threads = 0
        total_user_states = 0
        threads_insert_data = []
        user_states_update_data = []
        for board_id in THREAD_BOARDS:
            threads_file = os.path.join(DATA_DIR, f'{board_id}_threads.json')
            if os.path.exists(threads_file):
                threads_data = await asyncio.to_thread(_read_json_file, threads_file)
                for thread_id, info in threads_data.items():
                    created_dt = datetime.fromisoformat(info.get('created_at'))
                    threads_insert_data.append((
                        thread_id, board_id, info.get('op_id'), info.get('title'),
                        created_dt.timestamp(), 1 if info.get('is_archived') else 0
                    ))
                    total_threads += 1
            
            user_states_file = os.path.join(DATA_DIR, f'{board_id}_user_states.json')
            if os.path.exists(user_states_file):
                user_states = await asyncio.to_thread(_read_json_file, user_states_file)
                for user_id_str, state in user_states.items():
                    location = state.get('location', 'main')
                    if location != 'main':
                        user_states_update_data.append((location, int(user_id_str), board_id))
                        total_user_states += 1

        if threads_insert_data:
            await db.executemany(
                """
                INSERT OR REPLACE INTO Threads (thread_id, board_id, op_id, title, created_at, is_archived)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                threads_insert_data
            )

        if user_states_update_data:
            await db.executemany(
                "UPDATE Users SET location = ? WHERE user_id = ? AND board_id = ?",
                user_states_update_data
            )

        await db.commit()
        print(f"  > Готово. Мигрировано {total_threads} тредов и {total_user_states} состояний пользователей.")

        # 4. Миграция Постов (Posts) - только метаданные
        print("\n[4/5] Миграция метаданных постов...")
        total_posts = 0
        all_post_nums = set()
        posts_data = []
        for board_id in BOARDS:
            cache_file = f"{board_id}_reply_cache.json.gz"
            if not os.path.exists(cache_file):
                continue

            data = await asyncio.to_thread(_read_gzip_json_file, cache_file)

            meta_storage = data.get("messages_storage_meta", {})
            for post_num_str, meta in meta_storage.items():
                post_num = int(post_num_str)
                if post_num in all_post_nums:
                    continue # Пропускаем дубликаты
                
                timestamp_dt = datetime.fromisoformat(meta.get('timestamp'))

                # ВНИМАНИЕ: Содержимое поста (content) будет пустым json `{}`,
                # так как оно не сохранялось в кэше.
                posts_data.append((
                    post_num, meta.get('board_id'), meta.get('author_id'),
                    timestamp_dt.timestamp(), '{}'
                ))
                all_post_nums.add(post_num)
                total_posts += 1

        if posts_data:
            await db.executemany(
                """
                INSERT OR IGNORE INTO Posts (post_num, board_id, author_id, timestamp, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                posts_data
            )
        await db.commit()
        print(f"  > Готово. Мигрировано {total_posts} постов (только метаданные).")

        # 5. Обновление reply_to_post_num в постах (этот шаг требует, чтобы все посты уже были в БД)
        print("\n[5/5] Обновление связей ответов в постах...")
        # Этот этап требует дополнительной логики, которую мы пока опустим для простоты.
        # Для полноценной миграции ответов нужно будет собрать все reply и обновить посты.
        # Пока что оставляем этот функционал для будущих шагов.
        print("  > Шаг пропущен (будет реализован позже).")

    print("\n--- МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА ---")
    print(f"Теперь вы можете удалить JSON файлы и запустить бота с новой базой данных.")


if __name__ == "__main__":
    confirm = input("Вы уверены, что хотите перенести все данные из JSON в SQLite? "
                    "Это действие необратимо и должно выполняться на остановленном боте. (yes/no): ")
    if confirm.lower() == 'yes':
        asyncio.run(migrate())
    else:
        print("Миграция отменена.")
