import asyncio
import aiosqlite
import json
import time
from common.config import DB_NAME

TARGET_IDS = [280382, 280404, 280734, 280424] # Включая "хороший" для гарантии

async def main():
    print(" BDE-811: Starting Deep Database Repair...")
    
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # --- ШАГ 1: Синхронизация Threads и Posts ---
        print("\n[1/2] Syncing Posts and Threads tables...")

        chunk_size = 900
        posts_by_id = {}
        for i in range(0, len(TARGET_IDS), chunk_size):
            chunk = TARGET_IDS[i:i + chunk_size]
            if not chunk: continue
            placeholders = ', '.join(['?'] * len(chunk))
            query = f"SELECT * FROM Posts WHERE post_num IN ({placeholders})"
            async with db.execute(query, tuple(chunk)) as cursor:
                rows_post = await cursor.fetchall()
                for row in rows_post:
                    posts_by_id[row['post_num']] = dict(row)

        threads_to_delete = []
        threads_to_insert = []
        posts_to_update = []

        for pid in TARGET_IDS:
            post = posts_by_id.get(pid)
            if not post:
                print(f"  - Post #{pid} not found. Skipping.")
                continue

            # Удаляем старую запись в Threads, чтобы избежать конфликтов
            threads_to_delete.append((pid,))

            # Создаем новую, гарантированно корректную
            title = "Restored Thread"
            try:
                content_obj = json.loads(post['content'])
                text = content_obj.get('text', '')
                if text:
                    clean_text = ''.join(c for c in text if c.isprintable()).strip()
                    title = clean_text[:60] + "..." if len(clean_text) > 60 else clean_text
            except: pass

            threads_to_insert.append((
                str(pid), pid, post['board_id'], post['author_id'], title, post['timestamp'], time.time(), post.get('stream', 'ru')
            ))

            # Приводим типы к единому стандарту и обновляем флаги
            posts_to_update.append((str(pid), pid))

            print(f"  ✅ Synced thread #{pid}")

        if threads_to_delete:
            await db.executemany("DELETE FROM Threads WHERE thread_num = ?", threads_to_delete)

        if threads_to_insert:
            await db.executemany("""
                INSERT INTO Threads (thread_id, thread_num, board_id, op_id, title, created_at, last_updated_at, is_archived, stream)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, threads_to_insert)
            
        if posts_to_update:
            await db.executemany("""
                UPDATE Posts 
                SET thread_id = ?, is_shadow = 0, is_op_hidden = 0
                WHERE post_num = ?
            """, posts_to_update)

        # --- ШАГ 2: Полная пересборка FTS индекса ---
        print("\n[2/2] Rebuilding FTS index (this may take a minute)...")
        
        # Удаляем все старые записи из индекса
        await db.execute("DELETE FROM PostsFTS")
        
        last_id = 0
        chunk_size = 5000
        total_reindexed = 0
        while True:
            query = "SELECT post_num, content FROM Posts WHERE post_num > ? ORDER BY post_num ASC LIMIT ?"
            cursor = await db.execute(query, (last_id, chunk_size))
            rows = await cursor.fetchall()
            
            if not rows:
                break
                
            fts_data = []
            for row in rows:
                row_dict = dict(row) # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ
                try:
                    content_obj = json.loads(row_dict['content'])
                    text_content = content_obj.get('text', '')
                    if text_content and isinstance(text_content, str):
                        fts_data.append((row_dict['post_num'], text_content))
                except:
                    continue
            
            if fts_data:
                await db.executemany(
                    "INSERT INTO PostsFTS (rowid, content) VALUES (?, ?)",
                    fts_data
                )
                total_reindexed += len(fts_data)
                print(f"  - Re-indexed {total_reindexed} posts...")

            last_id = dict(rows[-1])['post_num'] # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ

        await db.commit()
        print(f"  ✅ FTS rebuild complete. Total posts indexed: {total_reindexed}.")
        
        print("  - Optimizing FTS index...")
        await db.execute("INSERT INTO PostsFTS(PostsFTS) VALUES('optimize');")
        await db.commit()

        print("\n🏁 Deep Repair finished.")

if __name__ == "__main__":
    asyncio.run(main())