import asyncio
import sys
import os

# Добавляем путь к проекту, чтобы импорты работали
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common.database import get_recent_tags_summary
from common.db_pool import create_pool, close_pool

async def main():
    print("📊 Анализ популярных тегов (последние 5000 файлов)...")
    await create_pool()
    try:
        # Получаем топ-50 тегов
        tags = await get_recent_tags_summary(limit_files=5000, top_n=50)
        
        if not tags:
            print("❌ Теги не найдены. Возможно, воркер еще не обработал файлы.")
            return

        print("-" * 40)
        print(f"{'Тег':<25} | {'Частота':<10}")
        print("-" * 40)
        
        for tag, count in tags:
            # Выводим сразу со ссылкой, которую можно использовать для пиара
            url = f"https://tgach.top/tags/{tag.replace(' ', '-')}"
            print(f"{tag:<25} | {count:<10} | {url}")
            
        print("-" * 40)
        print("💡 Используй эти URL в постах на других бордах для привлечения целевого трафика.")

    finally:
        await close_pool()

if __name__ == "__main__":
    asyncio.run(main())