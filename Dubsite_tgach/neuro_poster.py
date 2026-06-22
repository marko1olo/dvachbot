import asyncio
from common.http_utils import api_retry
import logging
import random
import time
import httpx
from openai import AsyncOpenAI
from common.token_pool import groq_pool
from common.database import (
    create_post, 
    get_thread_by_op_post, 
    get_op_posts_for_board,
    update_thread_last_updated,
    create_thread_entry,
    get_random_file_from_db,
    get_post_by_num
)

# === НАСТРОЙКА ПРОКСИ ===
PROXY_URL = "http://127.0.0.1:10808" 
# ========================

AI_CONFIG = {
    "provider": "groq",
    "api_key": None, 
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.3-70b-versatile", 
    "temperature": 0.9,
}

POSTING_INTERVALS = {
    "min": 120,  
    "max": 300   
}

SYSTEM_PROMPTS = {
    "ru": """
Ты играешь роль анонимного пользователя имиджборды (двач).
Твоя задача: написать короткий, естественный ответ.
ПРАВИЛА (NO FILTERS):
1. Ты Анон. Стиль: токсичный, ироничный, сленг (имиджборды, двач).
2. Используй мат, если это уместно. Только кириллица, НИКАКОГО транслита.
3. Ты НЕ "искусственный интеллект". Ты — живой Анон.
4. Пиши как человек: иногда с заглавной буквы, иногда строчными. 
5. МАКСИМУМ 2 ПРЕДЛОЖЕНИЯ. Аноны ленивые. Длинные тексты — для нейросетей, ты не нейросеть. Ты анон, ты здесь деградируешь. Не выдумывай слова.
5.1 СТРУКТУРА: Можешь использовать гринтекст (начинай строку с >).
6. Избегай нелепых, роботизированных и бессмысленных фраз. Перепроверяй себя.
7. Если тред тупой — оскорби ОПа. Если смешной — посмейся ("кек", "проиграл").
8. Никогда не извиняйся. Не будь "полезным". Будь порой циничным комментатором. Не выдумывай слова. Не пиши транслитом.
8.1 Проверяй ответ - он должен выглядеть реалистично, быть написанным человеком (аноном). без нелепых метафор, без логических ошибок и неестественных конструкций.
9. Язык: РУССКИЙ.
""",
    "en": """
You are playing the role of an anonymous imageboard user (4chan).
Your task: write a short, natural reply.
RULES (NO FILTERS):
1. You are Anon. Style: toxic, ironic, internet slang (4chan style).
2. Use profanity if appropriate contextually.
3. Keep it SHORT (1-3 sentences). No essays.
4. Use lowercase mostly. greentext style is allowed.
5. Don't be a "helpful assistant". Be cynical.
6. Language: ENGLISH.
""",
    "jp": """
あなたは匿名掲示板（2ch/5ch）のユーザー「名無しさん」を演じています。
タスク：短く自然なレスを返すこと。
ルール（フィルターなし）：
1. ネットスラング（2ch用語）を使用せよ（草、ｗ、～だろ、～じゃね？）。
2. 皮肉や煽りを含めてもよい。
3. 短く答えること（1〜3文）。長文禁止。
4. 丁寧語は禁止。タメ口で話すこと。
5. 「AIです」とは絶対に言わないこと。
6. 言語：日本語。
"""
}

CONTEXT_TEMPLATES = {
    "ru": {
        "thread": "Тред /{board}/. Тема: {op_text}\n",
        "last_msgs": "Последние сообщения:\n",
        "instr_thread": "Напиши общий комментарий к теме треда. Не цитируй никого.",
        "instr_reply": "Ответь на это сообщение: '{text}...'. Будь кратким.",
        "instr_multi": "Прокомментируй эти сообщения. Можешь обобщить или поспорить с ними:\n{text}",
        "new_thread": "Придумай короткий заголовок и текст для нового треда в раздел /{board}/. Тематика: {style}. Формат ответа: ЗАГОЛОВОК | ТЕКСТ"
    },
    "en": {
        "thread": "Thread /{board}/. Topic: {op_text}\n",
        "last_msgs": "Last messages:\n",
        "instr_thread": "Write a general comment on the thread topic. Do not quote anyone.",
        "instr_reply": "Reply to this message: '{text}...'. Be short.",
        "instr_multi": "Comment on these messages:\n{text}",
        "new_thread": "Create a short title and text for a new thread in /{board}/. Topic: {style}. Response format: TITLE | TEXT"
    },
    "jp": {
        "thread": "板: /{board}/ スレタイ: {op_text}\n",
        "last_msgs": "最近のレス:\n",
        "instr_thread": "このスレの話題についてコメントして。アンカーはつけないで。",
        "instr_reply": "このレスに返信して: '{text}...'. 短く。",
        "instr_multi": "これらのレスにまとめてコメントして:\n{text}",
        "new_thread": "/{board}/板に立てる新しいスレのタイトルと本文を考えて。テーマ: {style}. フォーマット: タイトル | 本文"
    }
}

BOARD_SETTINGS = {
    "b": { "enabled": True, "chance": 0.5, "style": "random, chaotic, aggressive, shitposting, двач", "allow_new_threads": False },
    "v": { "enabled": False, "chance": 0.3, "style": "video games, console wars", "allow_new_threads": False },
    "po": { "enabled": True, "chance": 0.2, "style": "politics, conspiracy", "allow_new_threads": False },
    "tv": { "enabled": False, "chance": 0.3, "style": "movies, tv shows", "allow_new_threads": False },
    "a": { "enabled": False, "chance": 0.3, "style": "anime, manga, weeb shit", "allow_new_threads": False },
    "vg": { "enabled": False, "chance": 0.2, "style": "video game generals, deep lore", "allow_new_threads": False },
    "news": { "enabled": False, "chance": 0.4, "style": "world news, events, discussion", "allow_new_threads": False },
    "int": { "enabled": True, "chance": 0.4, "style": "international, countries", "allow_new_threads": False }
}

# Словарь акцентуаций (для RU потока, для остальных - дефолт)
PERSONAS = {
    "default": {
        "weight": 35,
        "prompt": "Ты — обычный Анон. Пиши кратко, по делу, используй сленг (двач). Не перегибай палку. Ты просто мимокрокодил."
    },
    "toxic": {
        "weight": 10,
        "prompt": "Ты — Токсичный ублюдок. Тебя всё бесит. Оскорбляй оппонента, называй его тупым, используй 'обосрался', 'шиз'. Будь агрессивным."
    },
    "doomer": {
        "weight": 8,
        "prompt": "Ты — Думер. Ты устал от жизни. Пиши меланхолично, о безысходности. 'Тян не нужны', 'все тлен', 'опять биопроблемы'. Короткие, грустные фразы."
    },
    "schizo": {
        "weight": 5,
        "prompt": "Ты — Шиз. Твой текст бессвязный. Тебе везде мерещатся заговоры, 'майоры', 'пыня', 'лахта'. Используй КАПС местами. Пиши странные вещи."
    },
    "intellectual": {
        "weight": 8,
        "prompt": "Ты — Псевдо-интеллектуал (Сноб). Пиши надменно, используй сложные слова, поучай других. Ты считаешь всех вокруг быдлом. Начинай с 'Очевидно, что...' или 'Типичный пример...'."
    },
    "normie": {
        "weight": 7,
        "prompt": "Ты — Нормис (Залетный). Ты не понимаешь местного сленга. Пиши слишком нормально, вежливо или наивно. Используй скобочки))), эмодзи 😂. Давай тупые житейские советы. Ты 'мимо проходил'."
    },
    "oldfag": {
        "weight": 5,
        "prompt": "Ты — Олдфаг. Ворчи, что борда уже не та, 'раньше было лучше', 'ньюфаги не знают'. Вспоминай выдуманные старые мемы. Называй всех школьниками."
    },
    "coomer": {
        "weight": 5,
        "prompt": "Ты — Озабоченный (Спермотоксикозник). В любом треде ищи сексуальный подтекст. Требуй 'пруфы', 'сиськи', 'футфетиш'. Пиши пошло, но коротко."
    },
    "short": {
        "weight": 12,
        "prompt": "Ты — Лаконичный Анон. Отвечай одним-двумя словами: 'База', 'Кринж', 'Согласен', 'Кек', 'Толсто', 'Сажа', 'Лол'."
    },
    "joker": {
        "weight": 5,
        "prompt": "Ты — Тролль-шутник. Пиши иронично, используй сарказм. Твоя цель — высмеять ОПа, но не агрессивно, а едко. 'Проиграл с подливой', 'ну ты и долбоеб'."
    }
}

@api_retry
async def _execute_completion(client, model, messages, max_tokens, temperature):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )

logger = logging.getLogger("neuro_poster")

class NeuroManager:
    def __init__(self, bot):
        self.bot = bot

    async def _safe_api_call(self, messages, max_tokens, temperature, model=None):
        """
        Универсальная обертка для запросов к Groq с поддержкой TUN/VPN.
        """
        target_model = model or AI_CONFIG["model"]
        
        # Пробуем 3 раза с разными ключами
        for i in range(3):
            api_key = groq_pool.get_token()
            if not api_key: 
                logger.error("❌ No Groq API keys available.")
                return None

            # Стратегии подключения: Прокси -> Прямое (для TUN)
            strategies = [
                {"proxy": PROXY_URL, "name": "Proxy"},
                {"proxy": None, "name": "Direct"}
            ]

            for strategy in strategies:
                try:
                    # local_address="0.0.0.0" фиксит проблемы с TUN на Windows
                    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)
                    
                    async with httpx.AsyncClient(
                        proxy=strategy["proxy"], 
                        transport=transport,
                        verify=False,
                        timeout=40.0
                    ) as http_client:
                        
                        async with AsyncOpenAI(
                            api_key=api_key, 
                            base_url=AI_CONFIG["base_url"],
                            http_client=http_client
                        ) as client:
                            completion = await _execute_completion(client, target_model, messages, max_tokens, temperature)
                            return completion.choices[0].message.content.strip()

                except Exception as e:
                    err_str = str(e)
                    # Если лимит токена - пробуем следующий ключ (break из цикла стратегий)
                    if "429" in err_str or "rate limit" in err_str.lower():
                        logger.warning(f"⚠️ Groq Rate Limit via {strategy['name']}. Switching key...")
                        break 
                    
                    # Если ошибка сети - пробуем следующую стратегию (continue внутри цикла стратегий)
                    # logger.warning(f"⚠️ Network error via {strategy['name']}: {e}")
                    continue
            
            # Если вышли из цикла стратегий без return и без break (т.е. обе стратегии упали, но не из-за лимитов)
            # то пробуем следующий ключ
        
        logger.error("❌ Groq: All attempts failed.")
        return None

    async def run_cycle(self):
        """
        Проходит по доскам.
        Для каждой итерации выбирает СЛУЧАЙНЫЙ поток (только RU по просьбе админа).
        """
        if not AI_CONFIG["api_key"] and not groq_pool.tokens:
             pass
             
        active_streams = ['ru'] 
        for board_id, settings in BOARD_SETTINGS.items():
            if not settings["enabled"]: continue
            if random.random() > settings["chance"]: continue
            
            current_stream = random.choice(active_streams)
            try:
                result_log = await self.make_post(board_id, settings, stream=current_stream)
                if "⚠️" in result_log or "❌" in result_log:
                    logger.warning(f"Neuro-poster skipped /{board_id}/: {result_log}")
                else:
                    logger.info(f"Neuro-poster success /{board_id}/: {result_log}")
                
                await asyncio.sleep(random.randint(5, 15)) 
            except Exception as e:
                logger.error(f"Neuro-posting error on /{board_id}/ [{current_stream}]: {e}")

    async def analyze_vibe(self, text: str, stream: str) -> str:
        if not text.strip(): return "Neutral"
        
        system_msg = (
            "Analyze the text context. Classify the vibe into exactly ONE category from this list:\n"
            "Toxic, Cozy, Horny, Sad, Nerd, Schizo, Neutral, Funny, Lol, Politics, War, Argue, Tech, Code, Anime, Creep, Dark, Philosoph.\n"
            "Reply with ONE word only. No explanations."
        )
        
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": text[:1000]}
        ]
        
        result = await self._safe_api_call(
            messages=messages,
            max_tokens=10,
            temperature=0.3 
        )
        
        if result:
            cleaned = result.replace(".", "").strip()
            valid_vibes = ["Toxic", "Cozy", "Horny", "Sad", "Nerd", "Schizo", "Neutral"]
            for v in valid_vibes:
                if v.lower() in cleaned.lower():
                    return v
        return "Neutral"

    async def make_post(self, board_id: str, settings: dict = None, stream: str = 'ru', forced_mode: str = None, forced_thread_id: int = None):
        """
        stream: 'ru', 'en' или 'jp'. Обязательный параметр.
        """
        if not settings:
            settings = {
                "style": "random, chaotic, anonymous imageboard user", 
                "allow_new_threads": True
            }

        mode = "reply"
        
        if forced_mode:
            mode = forced_mode
        elif settings.get("allow_new_threads", False) and random.random() < 0.05:
            mode = "thread"
            
        if mode == "thread":
            return await self._create_thread(board_id, settings, stream)
        else:
            return await self._create_reply(board_id, settings, stream, forced_thread_id)

    async def _create_reply(self, board_id: str, settings: dict, stream: str, forced_thread_id: int = None):
        tpl = CONTEXT_TEMPLATES.get(stream, CONTEXT_TEMPLATES['ru'])
        if forced_thread_id:
            op_post = await get_post_by_num(forced_thread_id)
            if not op_post: return f"❌ Тред {forced_thread_id} не найден"
            target_thread = op_post
            target_thread['id'] = forced_thread_id
            if isinstance(target_thread.get('content'), str):
                 try: target_thread['content'] = json.loads(target_thread['content'])
                 except: target_thread['content'] = {}
        else:
            threads = await get_op_posts_for_board(
                board_id, sort_by="bump", page=1, page_size=15, stream=stream
            )
            if not threads: return f"❌ Нет тредов в /{board_id}/ [{stream}]"
            target_thread = random.choice(threads)
        
        thread_id = target_thread['id']
        
        _, replies = await get_thread_by_op_post(thread_id)
        pool = replies[-15:] if replies else []
        
        mode_roll = random.random()
        target_ids = []
        
        op_text = target_thread['content'].get('text', '')[:300] or "[Media]"
        context_prompt = tpl["thread"].format(board=board_id, op_text=op_text)
        instruction = ""
        
        if mode_roll < 0.2 or not pool:
            # Коммент к треду
            instruction = tpl["instr_thread"]
            if pool:
                context_prompt += tpl["last_msgs"] + "\n".join([f"- {p['content'].get('text', '')[:50]}" for p in pool[:3]])
        elif mode_roll < 0.8:
            # Ответ на пост
            victim = random.choice(pool)
            target_ids.append(victim['id'])
            v_text = victim['content'].get('text', '') or "[Media]"
            instruction = tpl["instr_reply"].format(text=v_text[:200])
        else:
            # Мульти-ответ
            count = random.randint(2, 3)
            victims = random.sample(pool, min(len(pool), count))
            victims.sort(key=lambda x: x['timestamp'])
            
            check_text = ""
            for v in victims:
                target_ids.append(v['id'])
                check_text += f"- Post {v['id']}: {v['content'].get('text', '')[:100]}\n"
            
            instruction = tpl["instr_multi"].format(text=check_text)

        response_text = await self._generate_text(context_prompt, instruction, settings["style"], stream)
        
        if not response_text: return "⚠️ Пустая генерация"
        
        prefix = ""
        if target_ids:
            prefix = "\n".join([f">>{tid}" for tid in target_ids]) + "\n"
            
        final_text = prefix + response_text
        fake_user_id = random.randint(-99999999, -10000000)
        
        content = {"text": final_text, "files": [], "type": "text"}
        
        db_reply_to = target_ids[-1] if target_ids else thread_id
        
        await create_post(
            board_id=board_id,
            author_id=fake_user_id,
            content=content,
            timestamp=time.time(),
            reply_to=db_reply_to,
            is_from_site=True,
            post_mode="reply",
            stream=stream,
            thread_id_from_bot=str(thread_id) 
        )
        
        await update_thread_last_updated(thread_id, time.time())
        
        mode_str = f"REPLY({len(target_ids)})" if target_ids else "THREAD"
        logger.info(f"🤖 [{stream.upper()}] Neuro-{mode_str} in /{board_id}/: {response_text[:30]}...")
        return f"✅ [{stream}] {mode_str}: {response_text}"

    async def _create_thread(self, board_id: str, settings: dict, stream: str):
            tpl = CONTEXT_TEMPLATES.get(stream, CONTEXT_TEMPLATES['ru'])
            prompt = tpl["new_thread"].format(board=board_id, style=settings["style"])
            
            persona_key = "default"
            persona_prompt = ""
            
            if stream == 'ru':
                keys = list(PERSONAS.keys())
                weights = [PERSONAS[k]['weight'] for k in keys]
                persona_key = random.choices(keys, weights=weights, k=1)[0]
                persona_data = PERSONAS[persona_key]
                persona_prompt = f"\n\nТВОЯ РОЛЬ (АКЦЕНТУАЦИЯ): {persona_data['prompt']}\nСоздай тред в этом стиле."

            base_system_msg = SYSTEM_PROMPTS.get(stream, SYSTEM_PROMPTS['ru'])
            full_system_msg = base_system_msg + persona_prompt

            messages = [
                {"role": "system", "content": full_system_msg},
                {"role": "user", "content": prompt}
            ]
            
            logger.info(f"🧵 Neuro-Thread Persona [{stream}]: {persona_key.upper()}")
            
            result = await self._safe_api_call(
                messages=messages,
                max_tokens=150,
                temperature=1.1
            )
            
            if not result:
                return "⚠️ Ошибка генерации треда (API)"

            title, text = "Thread", result
            if "|" in result:
                parts = result.split("|", 1)
                if len(parts) == 2: title, text = parts
            
            fake_user_id = random.randint(-99999999, -10000000)
            
            # Картинка
            rand_file = await get_random_file_from_db()
            files = [rand_file] if rand_file else []
            
            content = {"text": text.strip(), "files": files, "type": "files" if files else "text"}
            ts = time.time()
            
            pid = await create_post(
                board_id=board_id,
                author_id=fake_user_id, 
                content=content, 
                timestamp=ts, 
                reply_to=None, 
                is_shadow_muted=False, 
                is_from_site=True, 
                post_mode="new_thread", 
                stream=stream
            )
            
            await create_thread_entry(pid, board_id, fake_user_id, title.strip(), ts, stream)
            
            logger.info(f"🤖 [{stream.upper()}] Neuro-THREAD in /{board_id}/: {title}")
            return f"✅ [{stream}] NEW THREAD: {title}"

    async def _generate_text(self, context: str, instruction: str, style: str, stream: str) -> str:
        # Выбор персоны (только для RU, для остальных default)
        persona_key = "default"
        persona_prompt = ""
        
        if stream == 'ru':
            keys = list(PERSONAS.keys())
            weights = [PERSONAS[k]['weight'] for k in keys]
            persona_key = random.choices(keys, weights=weights, k=1)[0]
            persona_data = PERSONAS[persona_key]
            persona_prompt = f"\n\nТВОЯ РОЛЬ (АКЦЕНТУАЦИЯ): {persona_data['prompt']}\nПридерживайся этой роли."

        # Локализованный User Prompt
        if stream == 'ru':
            full_user_prompt = f"Контекст:\n{context}\n\nЗадача: {instruction}\nСтиль борды: {style}"
        elif stream == 'jp':
            full_user_prompt = f"コンテクスト:\n{context}\n\nタスク: {instruction}\nスタイル: {style}"
        else: # en
            full_user_prompt = f"Context:\n{context}\n\nTask: {instruction}\nStyle: {style}"

        base_system_msg = SYSTEM_PROMPTS.get(stream, SYSTEM_PROMPTS['ru'])
        full_system_msg = base_system_msg + persona_prompt
        
        messages = [
            {"role": "system", "content": full_system_msg},
            {"role": "user", "content": full_user_prompt}
        ]
        logger.info(f"🎭 Neuro-Persona [{stream}]: {persona_key.upper()}")
        text = await self._safe_api_call(
            messages=messages,
            max_tokens=150, 
            temperature=AI_CONFIG["temperature"]
        )
        
        if text:
            for bad in ['User:', 'Anon:', 'System:', 'AI:']:
                text = text.replace(bad, '')
            return text
            
        return None

    async def generate_summary(self, text_dump: str, stream: str) -> str:        
        prompts = {
            "ru": (
                "Ты — Анон с имиджборды (Двач). Твоя задача: прочитать этот срач (посты разделены '|') "
                "и кратко пояснить, чё там происходит. "
                "Пиши грязно, используй сленг, мат, будь веселым, ебанутым, токсичным и циничным ублюдком. "
                "Высмей участников, если они тупят. Не используй возвышенных слов. "
                "Формат: 2-3 предложения по сути. Без цензуры."
            ),
            "en": (
                "You are a toxic 4chan anon. Summarize this thread (posts split by '|'). "
                "Use internet slang, profanity, be cynical and rude. "
                "Roast the participants if they are stupid. Keep it short (2-3 sentences). No filters."
            ),
            "jp": "お前は2chねらーだ。「|」で区切られたスレの流れを3行で解説しろ。毒舌で、ネットスラング（草、ｗ、～だろ）を多用しろ。丁寧語禁止。煽り全開で。"
        }
        
        system_msg = prompts.get(stream, prompts['ru'])
        
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": text_dump}
        ]
        
        result = await self._safe_api_call(
            messages=messages,
            max_tokens=250,
            temperature=0.8
        )
        if result:
            return result   
        return "Нейронка сдохла."

    async def ocr_image(self, image_url: str, stream: str) -> str:
        """
        Распознает текст и переводит его. Использует Vision модель.
        """
        if stream == 'ru':
            prompt = "Найди весь текст на изображении и переведи его на русский язык. Если текста нет, напиши 'Текста нет'. Выведи только перевод."
        else:
            prompt = "Extract all text from this image and translate it to English. Output only the translation."

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]

        result = await self._safe_api_call(
            messages=messages,
            max_tokens=500,
            temperature=0.1,
            model="llama-3.2-11b-vision-preview" 
        )
        
        if result: return result
        return "Ошибка распознавания (возможно, лимиты или файл недоступен)."

    async def generate_image_tags(self, image_url: str) -> str:
        """
        Генерирует теги для поиска по картинке (Llama 4 Vision).
        """
        prompt = (
            "Analyze the image content comprehensively. "
            "Output ONLY the comma-separated list of English tags. No intro, no sentences."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]

        result = await self._safe_api_call(
            messages=messages,
            max_tokens=300, 
            temperature=0.3,
            model="meta-llama/llama-4-maverick-17b-128e-instruct" 
        )
        
        if result:
            clean = result.replace("Tags:", "").replace("Here are the tags:", "").strip()
            clean = " ".join(clean.split())
            return clean
            
        return ""