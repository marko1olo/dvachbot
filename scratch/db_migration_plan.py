import sqlite3
import json

def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Add missing is_shadow_reject column
    try:
        cursor.execute("ALTER TABLE Posts ADD COLUMN is_shadow_reject INTEGER DEFAULT 0")
        print("Added is_shadow_reject column.")
    except sqlite3.OperationalError:
        print("Column is_shadow_reject already exists.")

    # 2. Normalize JSON from Posts.content
    try:
        cursor.execute("ALTER TABLE Posts ADD COLUMN text_content TEXT")
        cursor.execute("ALTER TABLE Posts ADD COLUMN content_type TEXT")
        print("Added text_content and content_type columns.")
    except sqlite3.OperationalError:
        print("Columns for normalized content already exist.")

    # 3. Create PostFiles table for normalization
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS PostFiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_num INTEGER,
        file_type TEXT,
        original_file_id TEXT,
        thumbnail_file_id TEXT,
        original_url TEXT,
        thumbnail_url TEXT,
        FOREIGN KEY(post_num) REFERENCES Posts(post_num)
    )
    ''')

    # 4. Migrate data non-destructively
    cursor.execute("SELECT post_num, content FROM Posts")
    rows = cursor.fetchall()
    
    for post_num, content_json in rows:
        if not content_json:
            continue
        try:
            data = json.loads(content_json)
            text = data.get('text', None)
            c_type = data.get('type', None)
            
            cursor.execute(
                "UPDATE Posts SET text_content = ?, content_type = ? WHERE post_num = ?",
                (text, c_type, post_num)
            )
            
            files = data.get('files', [])
            for f in files:
                cursor.execute('''
                    INSERT INTO PostFiles (post_num, file_type, original_file_id, thumbnail_file_id, original_url, thumbnail_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    post_num, 
                    f.get('type'), 
                    f.get('original_file_id'), 
                    f.get('thumbnail_file_id'), 
                    f.get('original_url'), 
                    f.get('thumbnail_url')
                ))
        except Exception as e:
            print(f"Failed to parse or migrate post_num {post_num}: {e}")

    conn.commit()
    conn.close()
    print("Migration completed successfully (simulated).")

if __name__ == "__main__":
    migrate("C:/Users/danat/Desktop/dvachbot/dvach_bot.db")
