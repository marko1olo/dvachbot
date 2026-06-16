import asyncio
import logging
import httpx
import time
import json
import random
from common.config import STORAGE_CHANNELS, ADMIN_IDS
from common.bot_pool import global_bot_pool
from common.database import get_db_connection, get_system_setting, log_global_event
from site_tgach.importer import ThreadImporter
from site_tgach.neuro_poster import NeuroManager, AI_CONFIG

logger = logging.getLogger("neuro_scanner")

# Событие для мгновенного пробуждения
SCANNER_TRIGGER = asyncio.Event()

class NeuroScanner:
    def __init__(self, bot, neuro_manager: NeuroManager):
        self.bot = bot
        self.neuro = neuro_manager
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=3)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=30.0, 
            headers=headers, 
            follow_redirects=True,
            verify=False
        )
        self.seen_threads = set()

    async def close(self):
        await self.client.aclose()

    async def scan_and_schedule(self, board_source='b', target_board='b', target_stream='ru'):
        logger.info(f"🕵️ [Scanner] Scanning /{board_source}/ for content...")
        
        # 1. Скачиваем каталог (Используем прямой домен hk, который стабильнее отдает API)
        url = f"https://2ch.org/{board_source}/catalog.json"
        try:
            resp = await self.client.get(url, follow_redirects=True)
            
            # ПРОВЕРКА: Если Двач подсунул HTML (заглушку) вместо JSON
            content_type = resp.headers.get("content-type", "")
            if "application/json" not in content_type:
                logger.error(f"Scanner received non-JSON response ({content_type}) from {url}")
                return False

            if resp.status_code != 200:
                logger.error(f"Failed to fetch catalog: {resp.status_code}")
                return False
                
            data = resp.json()
        except Exception as e:
            logger.error(f"Catalog fetch error: {e}")
            return False

        threads = data.get('threads', [])
        candidates = []

        # 2. Hard Filter (базовый отсев)
        for t in threads:
            num = str(t.get('num'))
            posts_count = int(t.get('posts_count', 0))
            
            # Пропускаем уже импортированные (проверяем по БД ImportQueue/Requests)
            if await self._is_already_imported(num):
                continue
                
            # Лимиты постов
            if posts_count < 50 or posts_count > 350:
                continue
                
            # Пропускаем закрепленные и закрытые (обычно это правила)
            if t.get('closed') == 1 or t.get('sticky') == 1:
                continue

            comment = t.get('comment', '')[:500] # Берем начало текста
            subject = t.get('subject', '')
            
            # Предварительная оценка контента
            candidates.append({
                'num': num,
                'url': f"https://2ch.org/{board_source}/res/{num}.html",
                'posts_count': posts_count,
                'timestamp': int(t.get('timestamp', 0)),
                'subject': subject,
                'comment': comment,
                'score': 0
            })

        if not candidates:
            logger.info("🕵️ [Scanner] No suitable candidates found by hard filter.")
            return

        # Берем случайные 10 кандидатов для анализа (увеличили выборку)
        batch = random.sample(candidates, min(len(candidates), 10))
        
        best_candidate = None
        best_score = -1
        
        # 3. AI Filter (Асинхронно, макс 4 потока, с задержкой)
        sem = asyncio.Semaphore(4) # Ограничиваем одновременные запросы кол-вом ключей

        async def evaluate_wrapper(cand):
            async with sem:
                # Небольшая задержка, чтобы запросы не улетали на сервер Groq в одну миллисекунду
                await asyncio.sleep(random.uniform(0.5, 1.5)) 
                try:
                    score = await self._evaluate_thread_ai(cand['subject'], cand['comment'])
                except Exception as e:
                    logger.error(f"AI Eval error for {cand['num']}: {e}")
                    score = 0
                cand['score'] = score
                logger.info(f"   > Thread {cand['num']} score: {score}")
                return cand

        # Запускаем все проверки параллельно
        tasks = [evaluate_wrapper(c) for c in batch]
        evaluated_candidates = await asyncio.gather(*tasks)

        # Выбираем победителя
        for cand in evaluated_candidates:
            if cand['score'] > best_score:
                best_score = cand['score']
                best_candidate = cand

        # Порог качества (например, 7 из 10)
        if not best_candidate or best_score < 7:
            logger.info("🕵️ [Scanner] All candidates are trash (low score). Skipping.")
            return

        # 4. Расчет интервалов (Pacing)
        # Вычисляем "естественную" скорость треда
        life_time_seconds = time.time() - best_candidate['timestamp']
        if life_time_seconds < 1: life_time_seconds = 1
        
        avg_seconds_per_post = life_time_seconds / best_candidate['posts_count']
        
        # Маппинг на наши границы (1 мин ... 60 мин)
        # Если там постят каждые 10 сек -> у нас 1 мин
        # Если там постят раз в час -> у нас 60 мин
        
        target_avg = max(180, min(3600, avg_seconds_per_post)) # Clamp between 60s and 3600s
        
        # Делаем разброс +/- 30%
        interval_min = int(target_avg * 0.7)
        interval_max = int(target_avg * 1.3)
        
        # 5. Запуск Импорта
        logger.info(f"✅ [Scanner] WINNER: {best_candidate['subject']} (Score {best_score}). Starting import...")

        async with get_db_connection() as conn:
            await conn.execute(
                "INSERT INTO ImportRequests (user_id, url, target_board, comment, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (0, best_candidate['url'], target_board, "Neuro-Auto-Import", "approved", time.time())
            )
            await conn.commit()
        
        await self._notify_admin(best_candidate, interval_min, interval_max, target_board)
        
        sim_settings = {
            "enabled": True,
            "start_delay_mins": 1, # Начинаем почти сразу
            "interval_min": interval_min,
            "interval_max": interval_max
        }
        
        target_channel_id = STORAGE_CHANNELS.get(target_stream, STORAGE_CHANNELS['ru'])
        importer = ThreadImporter(self.bot, target_channel_id)
        
        # Запускаем в фоне
        asyncio.create_task(
            importer.process_thread(best_candidate['url'], target_board, target_stream, sim_settings)
        )
        return True

    async def _evaluate_thread_ai(self, subject: str, comment: str) -> int:
        """
        Спрашивает нейронку: "Это интересный тред или мусор?"
        """
        prompt = (
            "Analyze this 2ch thread OP post. \n"
            f"Subject: {subject}\n"
            f"Text: {comment}\n\n"
            "Task: Rate the thread quality for a general imageboard audience on a scale of 0 to 10.\n"
            "Criteria for HIGH score (7-10): Unique discussion, interesting story, 'lamp' atmosphere, original content.\n"
            "Criteria for LOW score (0-4): Spam, 'roll' threads, pure porn/fap threads, casino ads, unintelligible nonsense, repetetive 'bayan'.\n"
            "Output ONLY the number (integer). No text."
        )
        
        messages = [
            {"role": "system", "content": "You are a moderator of an imageboard. You filter trash."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            res = await self.neuro._safe_api_call(messages, max_tokens=5, temperature=0.1)
            if not res: return 0
            # Ищем число в ответе
            import re
            match = re.search(r'\d+', res)
            if match:
                return int(match.group(0))
            return 0
        except Exception:
            return 0

    async def _is_already_imported(self, orig_num: str) -> bool:
        """Проверяет, не импортировали ли мы этот тред ранее (по ID или URL)"""
        async with get_db_connection() as conn:
            # Проверяем в очереди импорта (active)
            res = await conn.execute(
                "SELECT 1 FROM ImportQueue WHERE original_post_num = ? LIMIT 1", 
                (orig_num,)
            )
            if await res.fetchone(): return True
            
            # Проверяем в выполненных заявках (history)
            # В ImportRequests мы храним URL.
            url_pattern = f"%/{orig_num}.html"
            res2 = await conn.execute(
                "SELECT 1 FROM ImportRequests WHERE url LIKE ? LIMIT 1",
                (url_pattern,)
            )
            if await res2.fetchone(): return True
            
        return False

    async def _notify_admin(self, thread_data, min_int, max_int, target_board):
        # Запись в лог админки
        log_text = f"🕵️ Scanner: Start import '{thread_data['subject']}' (Score: {thread_data['score']})"
        await log_global_event("bot", log_text)

        msg = (
            f"🤖 <b>Neuro-Scanner Report</b>\n\n"
            f"Нашел интересный тред и запустил симуляцию!\n"
            f"📌 <b>Тема:</b> {thread_data['subject'] or 'Без темы'}\n"
            f"📄 <b>Текст:</b> <i>{thread_data['comment'][:100]}...</i>\n"
            f"📊 <b>Постов:</b> {thread_data['posts_count']}\n"
            f"⭐ <b>AI Score:</b> {thread_data['score']}/10\n"
            f"⏱ <b>Интервал:</b> {min_int}-{max_int} сек.\n"
            f"🎯 <b>Цель:</b> /{target_board}/\n"
            f"🔗 <a href='{thread_data['url']}'>Оригинал</a>"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await self.bot.send_message(admin_id, msg, parse_mode="HTML")
            except: pass

async def scanner_loop(app_state):
    await asyncio.sleep(60)
    
    neuro_manager = app_state.neuro_manager
    bot = app_state.file_uploader_bot
    scanner = NeuroScanner(bot, neuro_manager)
    
    logger.info("👀 Neuro-Scanner Loop Started")
    
    try:
        while True:
            try:
                # 1. Проверяем, включен ли сканер
                enabled_str = await get_system_setting("neuro_scanner_enabled")

                # Если выключен — ждем либо 60 сек, либо пока не пнут (SCANNER_TRIGGER)
                if enabled_str != "true":
                    try:
                        await asyncio.wait_for(SCANNER_TRIGGER.wait(), timeout=60.0)
                        SCANNER_TRIGGER.clear() # Сбрасываем триггер после пробуждения
                        logger.info("👀 Scanner woke up by TRIGGER!")
                        continue # Сразу идем на новый виток цикла проверять настройки
                    except asyncio.TimeoutError:
                        continue # Просто прошло 60 сек, проверяем заново

                # 2. Читаем интервал
                interval_str = await get_system_setting("neuro_scanner_interval")
                try:
                    interval_minutes = int(interval_str)
                except (ValueError, TypeError):
                    interval_minutes = 66

                if interval_minutes < 10: interval_minutes = 10

                # 3. Сканируем
                success = await scanner.scan_and_schedule(board_source='b', target_board='b', target_stream='ru')

                # 4. Если ошибка сети — пробуем через 5 минут, если успех — через заданный интервал
                if success:
                    wait_seconds = (interval_minutes * 60) + random.randint(0, 300)
                    logger.info(f"👀 Scanner finished. Sleeping for {wait_seconds}s")
                else:
                    wait_seconds = 300
                    logger.warning(f"⚠️ Scanner failed. Retrying in {wait_seconds}s")

                await asyncio.sleep(wait_seconds)

            except Exception as e:
                logger.error(f"Scanner loop crash: {e}")
                await asyncio.sleep(300)
    finally:
        await scanner.close()
