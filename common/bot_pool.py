import os
import asyncio
import logging
import itertools
from typing import Optional, Tuple, Dict, List
from pathlib import Path
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from common.secret_redaction import install_logging_redaction, secret_fingerprint

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
install_logging_redaction()
logger = logging.getLogger("BotPool")

class MultiStreamBotPool:
    def __init__(self):
        self.iterators: Dict[str, itertools.cycle] = {}
        self.bots_map: Dict[str, Dict[int, Bot]] = {
            'ru': {}, 'en': {}, 'jp': {}
        }
        
        # Плоский список для закрытия сессий
        self.all_bots: List[Bot] = []
        
        # Кэш уникальных ботов, чтобы дубликаты токенов в .env не создавали лишние сессии aiohttp
        self._shared_bots: Dict[int, Bot] = {}
        
        # Множество загруженных потоков (защита от повторной загрузки)
        self._loaded_streams = set()
        
        # Множество отключенных/неактивных bot_id
        self.disabled_bot_ids = set()
        
        # Кулдауны ботов по времени (bot_id -> timestamp истечения)
        self.cooldown_bots: Dict[int, float] = {}

        # Обязательно добавляем основной BOT_TOKEN в кэш для возможности скачивания его файлов
        main_token = os.getenv("BOT_TOKEN")
        if main_token and ':' in main_token:
            try:
                bot_id = int(main_token.split(':')[0])
                bot = Bot(token=main_token, session=AiohttpSession())
                self._shared_bots[bot_id] = bot
                self.all_bots.append(bot)
            except Exception as e:
                logger.error(f"Error loading main BOT_TOKEN into BotPool: {e}")

    def _get_stream_pool(self, stream_code: str) -> str:
        if stream_code == 'en':
            return os.getenv("UPLOAD_BOT_POOL_EN", "")
        if stream_code == 'jp':
            return os.getenv("UPLOAD_BOT_POOL_JP", "")
        return os.getenv("UPLOAD_BOT_POOL_RU", "")

    def init_pool(self, stream: str = 'ru'):
        """Вызывается при старте сервера в main.py для предзагрузки основного пула."""
        self.init_stream(stream)

    def init_stream(self, stream_code: str):
        """Атомарная и ленивая инициализация пула для конкретного региона."""
        if stream_code in self._loaded_streams:
            return

        # Сразу ставим флаг, чтобы параллельные загрузки файлов (asyncio.gather) 
        # не запустили инициализацию одновременно (Race Condition)
        self._loaded_streams.add(stream_code)

        pool_str = self._get_stream_pool(stream_code)
        
        # Fallback для старых конфигов
        if stream_code == 'ru' and not pool_str:
            pool_str = os.getenv("UPLOAD_BOT_POOL", "")

        if not pool_str:
            return

        tokens = [t.strip() for t in pool_str.split(',') if t.strip()]
        bots_list = []

        for t in tokens:
            try:
                if ':' not in t: continue
                bot_id = int(t.split(':')[0])
                
                # Если бот помечен как мертвый, пропускаем
                if bot_id in self.disabled_bot_ids:
                    continue
                
                # Если бот уже есть в ЭТОМ пуле
                if bot_id in self.bots_map[stream_code]: 
                    continue
                
                # Если этот токен уже загружен другим потоком (например, EN берет из RU) - переиспользуем!
                if bot_id in self._shared_bots:
                    bot = self._shared_bots[bot_id]
                else:
                    # Создаем новую сессию только для уникальных токенов
                    bot = Bot(token=t, session=AiohttpSession())
                    self._shared_bots[bot_id] = bot
                    self.all_bots.append(bot)

                self.bots_map[stream_code][bot_id] = bot
                bots_list.append((bot_id, bot))
                
            except Exception as e:
                safe_token = secret_fingerprint(t)
                logger.error(f"❌ Error loading bot token '{safe_token}' for {stream_code}: {e}", exc_info=True)

        if bots_list:
            self.iterators[stream_code] = itertools.cycle(bots_list)
            logger.info(f"✅ Loaded {len(bots_list)} unique bots for stream '{stream_code}'")
        else:
            logger.warning(f"⚠️ No valid bots found for stream '{stream_code}'")

    def mark_bot_cooldown(self, bot_id: int, duration_sec: float = 15.0):
        """Отправляет бота в кулдаун при TelegramRetryAfter/FloodWait (по умолчанию 15 секунд)."""
        import time
        cooldown_until = time.time() + max(15.0, duration_sec)
        self.cooldown_bots[bot_id] = cooldown_until
        logger.warning(f"⏳ Bot {bot_id} put on FloodWait cooldown for {max(15.0, duration_sec):.1f}s (until {cooldown_until:.1f})")

    def mark_bot_cooldown_by_bot(self, bot: Bot, duration_sec: float = 15.0):
        """Ставит бота в кулдаун по объекту Bot (извлекая bot_id)."""
        if not bot:
            return
        bot_id = getattr(bot, 'id', None)
        if not bot_id and hasattr(bot, 'token') and ':' in str(bot.token):
            try:
                bot_id = int(str(bot.token).split(':', 1)[0])
            except (ValueError, TypeError):
                pass
        if bot_id:
            self.mark_bot_cooldown(bot_id, duration_sec=duration_sec)

    def is_bot_on_cooldown(self, bot_id: int) -> bool:
        """Проверяет, находится ли бот на временном кулдауне."""
        import time
        return self.cooldown_bots.get(bot_id, 0) > time.time()

    def get_next_bot(self, stream: str = 'ru') -> Tuple[int, Bot]:
        """Возвращает следующего доступного бота для загрузки (Round-Robin с обходом кулдауна)."""
        import time
        # Грузим только запрошенный поток
        self.init_stream(stream)
        
        target_stream = stream if stream in self.iterators else 'ru'
        if target_stream not in self.iterators:
            # Если запрошенного нет, принудительно грузим RU как фоллбэк
            self.init_stream('ru')
            target_stream = 'ru'
            
        if target_stream not in self.iterators:
            raise ValueError(f"No bots available for stream {stream} or ru!")

        now = time.time()
        bots_map = self.bots_map.get(target_stream, {})
        total_bots = len(bots_map)
        
        # Проверяем ботов по кругу, пропуская находящихся на кулдауне
        best_candidate = None
        earliest_expiry = float('inf')

        for _ in range(max(1, total_bots)):
            bot_id, bot = next(self.iterators[target_stream])
            cooldown_until = self.cooldown_bots.get(bot_id, 0)
            if cooldown_until <= now:
                return bot_id, bot
            
            if cooldown_until < earliest_expiry:
                earliest_expiry = cooldown_until
                best_candidate = (bot_id, bot)

        # Если все боты на кулдауне, берем того, у кого кулдаун истекает раньше всех
        if best_candidate:
            return best_candidate

        return next(self.iterators[target_stream])

    def get_bot_by_id(self, bot_id: int) -> Optional[Bot]:
        """Ищет бота по ID сперва в кэше, затем по остальным пулам."""
        if bot_id in self._shared_bots:
            return self._shared_bots[bot_id]
            
        # Если не нашли, придется лениво подгрузить остальные потоки, чтобы найти владельца
        for s in ['ru', 'en', 'jp']:
            if s not in self._loaded_streams:
                self.init_stream(s)
                if bot_id in self._shared_bots:
                    return self._shared_bots[bot_id]
        return None
    
    def get_all_active_bots(self, prioritize_ready: bool = True) -> List[Bot]:
        """
        Все уникальные живые боты по всем потокам.
        Если prioritize_ready=True, боты не на кулдауне идут первыми.

        Нужен для фолбэка при скачивании файлов: file_id принадлежит выдавшему
        его боту, остальные получают 'file not found', поэтому приходится
        перебирать весь пул.
        """
        import time
        for stream_code in ('ru', 'en', 'jp'):
            self.init_stream(stream_code)
        
        now = time.time()
        active_items = [
            (bot_id, bot) for bot_id, bot in self._shared_bots.items()
            if bot_id not in self.disabled_bot_ids
        ]
        if not prioritize_ready:
            return [bot for _, bot in active_items]

        ready_bots = []
        cooling_bots = []
        for bot_id, bot in active_items:
            cd_until = self.cooldown_bots.get(bot_id, 0)
            if cd_until <= now:
                ready_bots.append(bot)
            else:
                cooling_bots.append((cd_until, bot))
        cooling_bots.sort(key=lambda x: x[0])
        return ready_bots + [b for _, b in cooling_bots]

    def get_download_candidates(self, primary_bot: Optional[Bot] = None) -> List[Bot]:
        """
        Формирует оптимальный список ботов-кандидатов для скачивания медиа:
        1. Владелец файла (если жив и не в кулдауне)
        2. Главный бот (если жив и не в кулдауне)
        3. Другие активные боты, готовые к работе (не в кулдауне)
        4. Владелец файла (если был в кулдауне)
        5. Остальные боты в кулдауне (в порядке скорейшего выхода из кулдауна)
        """
        import time
        now = time.time()
        for stream_code in ('ru', 'en', 'jp'):
            self.init_stream(stream_code)

        candidates = []
        seen = set()

        def _get_bid(b):
            bid = getattr(b, 'id', None)
            if not bid and hasattr(b, 'token') and ':' in str(b.token):
                try:
                    bid = int(str(b.token).split(':', 1)[0])
                except (ValueError, TypeError):
                    pass
            return bid or id(b)

        # 1. Primary bot if ready
        if primary_bot:
            p_id = _get_bid(primary_bot)
            if p_id not in self.disabled_bot_ids:
                if self.cooldown_bots.get(p_id, 0) <= now:
                    candidates.append(primary_bot)
                    seen.add(p_id)

        # 2. Main bot if ready and not seen
        main_bot = self.get_main_bot()
        if main_bot:
            m_id = _get_bid(main_bot)
            if m_id not in seen and m_id not in self.disabled_bot_ids:
                if self.cooldown_bots.get(m_id, 0) <= now:
                    candidates.append(main_bot)
                    seen.add(m_id)

        # 3. All other active ready bots
        cooling = []
        for b_id, b in self._shared_bots.items():
            if b_id in seen or b_id in self.disabled_bot_ids:
                continue
            cd_until = self.cooldown_bots.get(b_id, 0)
            if cd_until <= now:
                candidates.append(b)
                seen.add(b_id)
            else:
                cooling.append((cd_until, b_id, b))

        # 4. If primary bot was on cooldown, add it before other cooling bots
        if primary_bot:
            p_id = _get_bid(primary_bot)
            if p_id not in seen and p_id not in self.disabled_bot_ids:
                candidates.append(primary_bot)
                seen.add(p_id)

        # 5. Cooling bots ordered by expiration
        cooling.sort(key=lambda x: x[0])
        for _, b_id, b in cooling:
            if b_id not in seen:
                candidates.append(b)
                seen.add(b_id)

        return candidates

    def get_main_bot(self) -> Optional[Bot]:
        """Возвращает 'главного' бота (первый из RU пула)."""
        self.init_stream('ru')
        ru_bots = self.bots_map.get('ru')
        if ru_bots:
            return next(iter(ru_bots.values()))
        if self.all_bots:
            return self.all_bots[0]
        return None

    def mark_bot_dead(self, bot_id: int):
        """Помечает бота как неактивного (logged out) и удаляет из всех пулов и итераторов."""
        if bot_id in self.disabled_bot_ids:
            return

        self.disabled_bot_ids.add(bot_id)
        logger.warning(f"🚨 Bot {bot_id} is logged out/dead. Disabling across all streams.")

        # Удаляем из кэша уникальных ботов
        bot = self._shared_bots.pop(bot_id, None)
        if bot:
            if bot in self.all_bots:
                self.all_bots.remove(bot)
            # Закрываем сессию асинхронно с проверкой наличия event loop.
            # Через spawn_task, а не голым loop.create_task: цикл событий
            # держит на задачу только СЛАБУЮ ссылку, и задача без своей
            # ссылки может быть собрана сборщиком мусора прямо во время
            # выполнения. Тогда сессия aiohttp мёртвого бота не закрывалась
            # бы никогда - утечка сокета и памяти на каждом разлогине.
            # Ровно для этого в проекте есть task_manager, через него идут
            # все 162 остальные фоновые задачи; это место было единственным
            # в обход. Он же логирует падение с именем задачи.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                import traceback; traceback.print_exc()
            else:
                from common.task_manager import spawn_task
                spawn_task(self._close_bot_session(bot))

        # Удаляем из bots_map во всех регионах и перестраиваем итераторы
        for stream_code, bots in self.bots_map.items():
            if bot_id in bots:
                del bots[bot_id]
                bots_list = list(bots.items())
                if bots_list:
                    self.iterators[stream_code] = itertools.cycle(bots_list)
                    logger.info(f"🔄 Rebuilt iterator for '{stream_code}', remaining: {len(bots_list)}")
                else:
                    self.iterators.pop(stream_code, None)
                    logger.warning(f"⚠️ No active bots left for stream '{stream_code}'!")

    def mark_bot_dead_by_token(self, token: str):
        """Вспомогательный метод для удаления бота по токену."""
        if not token or ':' not in str(token):
            return
        try:
            bot_id = int(str(token).split(':', 1)[0])
            self.mark_bot_dead(bot_id)
        except (TypeError, ValueError):
            import traceback; traceback.print_exc()

    async def _close_bot_session(self, bot: Bot):
        try:
            await bot.session.close()
            logger.info("🔌 Closed session for disabled bot")
        except Exception as e:
            logger.error(f"Error closing disabled bot session: {e}", exc_info=True)

    async def close_all(self):
        logger.info("🔌 Closing all bot sessions...")
        for bot in self.all_bots:
            try:
                await bot.session.close()
            except: 
                pass

# Создаем глобальный экземпляр
try:
    global_bot_pool = MultiStreamBotPool()
except Exception as e:
    logger.critical(f"Failed to init BotPool: {e}")
    global_bot_pool = None
