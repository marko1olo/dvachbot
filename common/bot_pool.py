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
        self.all_bots: List[Bot] =[]
        
        # Кэш уникальных ботов, чтобы дубликаты токенов в .env не создавали лишние сессии aiohttp
        self._shared_bots: Dict[int, Bot] = {}
        
        # Множество загруженных потоков (защита от повторной загрузки)
        self._loaded_streams = set()

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

        tokens =[t.strip() for t in pool_str.split(',') if t.strip()]
        bots_list =[]

        for t in tokens:
            try:
                if ':' not in t: continue
                bot_id = int(t.split(':')[0])
                
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
                logger.error(f"❌ Error loading bot token '{safe_token}' for {stream_code}: {e}")

        if bots_list:
            self.iterators[stream_code] = itertools.cycle(bots_list)
            logger.info(f"✅ Loaded {len(bots_list)} unique bots for stream '{stream_code}'")
        else:
            logger.warning(f"⚠️ No valid bots found for stream '{stream_code}'")

    def get_next_bot(self, stream: str = 'ru') -> Tuple[int, Bot]:
        """Возвращает следующего бота для загрузки (Round-Robin)."""
        # Грузим только запрошенный поток
        self.init_stream(stream)
        
        target_stream = stream if stream in self.iterators else 'ru'
        if target_stream not in self.iterators:
            # Если запрошенного нет, принудительно грузим RU как фоллбэк
            self.init_stream('ru')
            target_stream = 'ru'
            
        if target_stream not in self.iterators:
            raise ValueError(f"No bots available for stream {stream} or ru!")
            
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
    
    def get_main_bot(self) -> Optional[Bot]:
        """Возвращает 'главного' бота (первый из RU пула)."""
        self.init_stream('ru')
        ru_bots = self.bots_map.get('ru')
        if ru_bots:
            return next(iter(ru_bots.values()))
        if self.all_bots:
            return self.all_bots[0]
        return None

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
