# validate_data.py
import json
import os
from collections import Counter

IMPORT_DIR = "data_export"

def validate():
    print("--- Запуск скрипта валидации экспортных данных ---")

    boards_file = os.path.join(IMPORT_DIR, "Boards.json")
    posts_file = os.path.join(IMPORT_DIR, "Posts.json")

    if not os.path.exists(boards_file) or not os.path.exists(posts_file):
        print("⛔ Ошибка: Не найдены файлы Boards.json и/или Posts.json в папке data_export.")
        return

    # 1. Загружаем все валидные ID досок
    with open(boards_file, 'r', encoding='utf-8') as f:
        boards_data = json.load(f)
    valid_board_ids = {board['board_id'] for board in boards_data}
    print(f"✅ Найдено {len(valid_board_ids)} валидных досок: {list(valid_board_ids)}")

    # 2. Проверяем все посты
    with open(posts_file, 'r', encoding='utf-8') as f:
        posts_data = json.load(f)
    
    print(f"Анализирую {len(posts_data)} постов...")
    
    invalid_posts = []
    for post in posts_data:
        board_id = post.get('board_id')
        if board_id not in valid_board_ids:
            invalid_posts.append(post)

    # 3. Выводим результат
    if not invalid_posts:
        print("\n--- ✅ ВАЛИДАЦИЯ УСПЕШНА: Все посты ссылаются на существующие доски. ---")
        print("Проблема может быть в чем-то другом. Это неожиданный результат.")
    else:
        print(f"\n--- ⛔ ВАЛИДАЦИЯ ПРОВАЛЕНА: Найдено {len(invalid_posts)} постов с некорректным board_id! ---")
        
        invalid_board_ids = [post.get('board_id') for post in invalid_posts]
        id_counts = Counter(invalid_board_ids)
        
        print("\nРаспределение по некорректным board_id:")
        for board_id, count in id_counts.items():
            print(f" - ID доски '{board_id}': {count} постов")
            
        print("\nПримеры некорректных постов (первые 5):")
        for i, post in enumerate(invalid_posts[:5]):
            print(f" {i+1}. post_num: {post.get('post_num')}, board_id: '{post.get('board_id')}'")

    print("\n--- Проверка завершена. ---")

if __name__ == "__main__":
    validate()