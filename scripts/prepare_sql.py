import os

INPUT_FILE = "backup.sql"
OUTPUT_FILE = "clean_import.sql"

def fix_dump_final():
    print(f"🔧 Финальная чистка {INPUT_FILE}...")
    
    if not os.path.exists(INPUT_FILE):
        print("❌ Файл backup.sql не найден!")
        return

    lines_kept = 0
    lines_skipped = 0
    
    skip_trigger = False
    skip_fts_multiline = False

    with open(INPUT_FILE, 'r', encoding='utf-8', errors='replace') as fin:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as fout:
            
            # Настройки
            fout.write("PRAGMA foreign_keys = OFF;\n")
            fout.write("PRAGMA synchronous = OFF;\n")
            fout.write("PRAGMA journal_mode = WAL;\n")
            fout.write("BEGIN TRANSACTION;\n")
            
            # Пустая таблица FTS (заглушка)
            fout.write("CREATE VIRTUAL TABLE IF NOT EXISTS PostsFTS USING fts5(content, content='Posts', content_rowid='post_num');\n")

            for line in fin:
                line_strip = line.strip()

                # 1. Удаляем sqlite_stat (ИСТОЧНИК ТВОЕЙ ОШИБКИ)
                if "sqlite_stat" in line:
                    lines_skipped += 1
                    continue

                # 2. Удаляем sqlite_sequence (на всякий случай, он пересоздастся сам)
                if "sqlite_sequence" in line:
                    lines_skipped += 1
                    continue

                # 3. Удаляем ТРИГГЕРЫ
                if "CREATE TRIGGER" in line:
                    skip_trigger = True
                
                if skip_trigger:
                    lines_skipped += 1
                    if line_strip.endswith("END;"):
                        skip_trigger = False
                    continue

                # 4. Удаляем FTS (системные таблицы поиска)
                if "PostsFTS" in line:
                    if "CREATE" in line or "INSERT INTO" in line or "DROP TABLE" in line:
                        lines_skipped += 1
                        if not line_strip.endswith(";"):
                            skip_fts_multiline = True
                        continue
                
                if skip_fts_multiline:
                    lines_skipped += 1
                    if line_strip.endswith(";"):
                        skip_fts_multiline = False
                    continue

                # 5. Убираем лишние транзакции из файла
                if "BEGIN TRANSACTION" in line or "COMMIT" in line:
                    continue

                # 6. Убираем системный мусор
                if "sqlite_master" in line:
                    continue

                # ВСЁ ОСТАЛЬНОЕ ПИШЕМ
                fout.write(line)
                lines_kept += 1
                
                if lines_kept % 200000 == 0:
                    print(f"⏳ Живых строк: {lines_kept}...", end='\r')

            fout.write("\nCOMMIT;")
    
    print(f"\n✅ Файл готов: {OUTPUT_FILE}")
    print(f"🗑️ Вырезано мусора: {lines_skipped}")
    print("👉 Выполняй: sqlite3.exe dvach_bot.db < clean_import.sql")

if __name__ == "__main__":
    fix_dump_final()