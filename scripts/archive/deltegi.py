import asyncio
import os
import sys
from collections import Counter

# --- НАЧАЛО: Настройка путей для импорта ---
# Это необходимо, чтобы скрипт мог найти ваши модули `common`
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)
# --- КОНЕЦ: Настройка путей ---

from common.db_pool import create_pool, get_pool, close_pool

async def main():
    """
    Основная функция для очистки и анализа тегов в базе данных.
    """
    await create_pool()
    db = await get_pool()

    print("--- Запуск анализа и очистки тегов ---")

    try:
        # 1. Получаем все записи, у которых есть теги
        print("1/5: Загрузка всех тегов из базы данных...")
        async with db.execute("SELECT rowid, file_id, tags FROM FileRegistry WHERE tags IS NOT NULL AND tags != ''") as cursor:
            all_records = await cursor.fetchall()
        
        if not all_records:
            print("Теги не найдены. Завершение.")
            return

        print(f"   => Найдено {len(all_records)} записей с тегами.")

        # 2. Очистка точек и подсчет статистики
        print("2/5: Анализ тегов и удаление точек на конце...")
        tag_counter = Counter()
        updates_for_dots = {}
        
        # Словарь для хранения очищенных данных для следующего шага
        cleaned_records = {}

        for rowid, file_id, tags_str in all_records:
            # Разделяем теги и чистим каждый от пробелов и точек в конце
            original_tags = [t.strip() for t in tags_str.split(',')]
            cleaned_tags = [t.rstrip('.').strip() for t in original_tags]
            
            # Обновляем счетчик популярности уже очищенными тегами
            tag_counter.update(tag for tag in cleaned_tags if tag)

            # Собираем строку обратно
            new_tags_str = ','.join(cleaned_tags)
            
            # Если строка изменилась, готовим ее к обновлению
            if new_tags_str != tags_str:
                updates_for_dots[rowid] = new_tags_str
            
            # Сохраняем очищенную версию для следующего шага
            cleaned_records[rowid] = (file_id, new_tags_str)

        print(f"   => Найдено {len(updates_for_dots)} записей с некорректными точками.")
        
        # 3. Поиск и удаление редких тегов
        print("3/5: Поиск и удаление редких тегов (менее 2 упоминаний)...")
        
        # Находим все теги, которые встречаются реже 2 раз
        rare_tags = {tag for tag, count in tag_counter.items() if count < 2}
        
        updates_for_rarity = {}
        
        for rowid, (file_id, tags_str) in cleaned_records.items():
            # Фильтруем теги, убирая редкие
            original_tags = [t.strip() for t in tags_str.split(',')]
            frequent_tags = [tag for tag in original_tags if tag not in rare_tags]
            
            new_tags_str = ','.join(frequent_tags)
            
            # Если строка изменилась после удаления редких тегов
            if new_tags_str != tags_str:
                updates_for_rarity[rowid] = new_tags_str

        print(f"   => Найдено {len(rare_tags)} уникальных редких тегов.")
        print(f"   => Обновлено {len(updates_for_rarity)} записей после удаления редких тегов.")

        # 4. Объединение изменений и запись в БД
        # Обновляем словарь: сначала применяются изменения от точек, потом от редких тегов
        final_updates = updates_for_dots.copy()
        final_updates.update(updates_for_rarity)

        if final_updates:
            print(f"4/5: Сохранение {len(final_updates)} изменений в базу данных...")
            update_data = [(tags, rowid) for rowid, tags in final_updates.items()]
            
            await db.executemany(
                "UPDATE FileRegistry SET tags = ? WHERE rowid = ?",
                update_data
            )
            await db.commit()
            print("   => Изменения успешно сохранены.")
        else:
            print("4/5: База данных уже в актуальном состоянии, изменения не требуются.")

        # 5. Вывод отчета
        print("\n--- Итоговый отчет ---")
        print(f"Всего проанализировано записей: {len(all_records)}")
        print(f"Исправлено записей с точкой на конце: {len(updates_for_dots)}")
        print(f"Найдено и удалено редких тегов: {len(rare_tags)}")
        print(f"Всего обновлено записей в БД: {len(final_updates)}")
        
        print("\nТоп-50 самых популярных тегов:")
        top_50 = tag_counter.most_common(50)
        for i, (tag, count) in enumerate(top_50, 1):
            print(f"{i:2}. {tag:<25} ({count} раз)")

    except Exception as e:
        print(f"\n⛔ Произошла ошибка: {e}")
        if db.in_transaction:
            await db.rollback()
    finally:
        await close_pool()
        print("\n--- Работа скрипта завершена ---")


if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(main())