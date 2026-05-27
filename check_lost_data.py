import os

INPUT_FILE = "backup.sql"

def check_skipped():
    print(f"🕵️ Анализирую, что мы собираемся удалить из {INPUT_FILE}...")
    
    skipped_count = 0
    samples = []
    
    with open(INPUT_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Логика та же, что и в фиксере
            if "PostsFTS" in line and ("CREATE VIRTUAL TABLE" in line or "INSERT INTO" in line):
                skipped_count += 1
                if len(samples) < 5:  # Сохраним первые 5 примеров
                    samples.append(line.strip())
                elif skipped_count > 12000 and len(samples) < 10: # И последние (примерно)
                    samples.append(line.strip())

    print(f"\n📊 Всего кандидатов на удаление: {skipped_count}")
    print("\n--- ПРИМЕРЫ ТОГО, ЧТО БУДЕТ УДАЛЕНО ---")
    for s in samples:
        # Обрезаем очень длинные строки для читаемости
        print(s[:150] + "..." if len(s) > 150 else s)
    print("---------------------------------------")
    
    print("\nИТОГ:")
    print("Если строки выглядят как: INSERT INTO \"PostsFTS_data\" VALUES(1, ...куча цифр или крокозябры...)")
    print("ИЛИ: INSERT INTO \"PostsFTS\" VALUES('текст поста', ...)")
    print("✅ ЭТО БЕЗОПАСНО. Это просто дубликат для поиска. Сами посты лежат в таблице 'Posts' и они ОСТАНУТСЯ.")

if __name__ == "__main__":
    check_skipped()