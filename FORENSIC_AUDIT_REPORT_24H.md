# СУДЕБНЫЙ АУДИТ СИСТЕМНЫХ СБОЕВ И ЛОГОВ (24 ЧАСА)
**Временное окно аудита:** `2026-09-09 19:38:00` — `2026-09-10 19:42:00` MSK/UTC+4  
**Рабочий каталог:** `c:\Users\danat\Desktop\dvachbot`  
**Исследованные логи:**
- `logs/bot_stdout_utf8.log` (312.4 MB, срез за 24ч: 1.28 MB, ~9500 строк)
- `logs/bot_runtime.log` (1.29 MB, срез за 24ч: 1572 строки)
- `logs/bot_fatal_crash.log` (246 KB)
- `logs/bot_supervisor.log` (430 KB)
- `logs/bot_deadlock_watchdog.log` (481 KB)
- `media_processor.log` (8.3 KB)

---

## 1. АНАЛИЗ ИСКЛЮЧЕНИЙ И PYTHON TRACEBACK

### 1.1. Проверка повтора ошибки `TypeError: unsupported operand type(s) for -: 'float' and 'datetime.datetime'`
- **Статус:** **ПОЛНОСТЬЮ УСТРАНЕНА, ПОВТОРОВ НЕТ (0 повторов после рестарта).**
- **Хронология инцидента:**
  1. **До фикса (до 12:10:12 2026-09-10):**
     - Зафиксировано **3 падения** в `schedule_persona_reply` (посты 522905 на `/vg/`, 522955 на `/b/` и др.) с сообщением:
       `Error in schedule_persona_reply: unsupported operand type(s) for -: 'float' and 'datetime.datetime'`.
     - Зафиксирован **1 критический сбой** в `task_manager` с полным Traceback в `12:02:06`:
       ```text
       2026-09-10 12:02:06,612 - task_manager - ERROR - Фоновая задача 'trigger_cyberchad_with_rate_limit' завершилась с ошибкой: TypeError: unsupported operand type(s) for -: 'float' and 'datetime.datetime'
       Traceback (most recent call last):
         File "C:\Users\danat\Desktop\dvachbot\handlers\message_router.py", line 475, in trigger_cyberchad_with_rate_limit
           await register_post_and_maybe_trigger_cyberchad_intervention(...)
         File "C:\Users\danat\Desktop\dvachbot\ai_manager.py", line 3743, in register_post_and_maybe_trigger_cyberchad_intervention
           rich_context = await build_cyberchad_context(...)
         File "C:\Users\danat\Desktop\dvachbot\ai_manager.py", line 3177, in build_cyberchad_context
           if p_ts and (now_ts - p_ts > 7200.0) and not in_test_env:
                        ~~~~~~~^~~~~~
       TypeError: unsupported operand type(s) for -: 'float' and 'datetime.datetime'
       ```
  2. **Применение патча:** В `12:04:10` скрипт `scratch/patch_timestamp_fix.py` применил валидацию типов `p_ts` (преобразование `datetime.datetime` через `.timestamp()`).
  3. **Перезапуск процесса:** В `12:10:12` супервизор запустил новый дочерний процесс `PID=12328`.
  4. **После фикса (с 12:10:12 до 19:42):**
     - За более чем 7.5 часов активной генерации Киберчеда, диалогов и постов в `ai_manager.py` и `handlers/message_router.py` зафиксировано **0 повторов**.

---

### 1.2. Другие исключения в коде (`task_manager`, `delivery_manager`, `main.py`)
1. **[КРИТИЧЕСКИЙ БАГ] `NameError: name 'os' is not defined` в `delivery_manager.py`**
   - **Частота:** 4 раза за сутки (`2026-09-10 17:02:31`, `17:10:18` на досках `/b/` и `/sex/`).
   - **Лог:** `❌ [b] Ошибка в board_help_worker: name 'os' is not defined`
   - **Локация:** `delivery_manager.py`, строка 1369 в функции `board_help_worker`:
     ```python
     if not fid and hasattr(photo_payload, 'path') and os.path.exists(photo_payload.path):
     ```
   - **Причина:** В модуле `delivery_manager.py` отсутствовал импорт `import os`. При генерации баннера помощи с объектом файла воркер падал и прерывал регулярную рассылку помощи.
   - **Статус исправления:** **ИСПРАВЛЕНО НА МЕСТЕ.** В начало `delivery_manager.py` добавлен `import os`, синтаксис проверен (`py_compile` exit code 0).

2. **[СЕТЕВОЙ СБОЙ] Обрыв связи ОС на Windows (WinError 64)**
   - **Время:** `2026-09-10 17:32:43`
   - **Лог:**
     ```text
     2026-09-10 17:32:43,184 - asyncio - ERROR - Future exception was never retrieved
     future: <Future finished exception=ConnectionError('Connection lost')>
     aiohttp.client_exceptions.ClientOSError: [WinError 64] The specified network name is no longer available
     ConnectionError: Connection lost
     💔 Сбой Heartbeat #1: TelegramNetworkError ... #19
     💀 СЕТЬ МЕРТВА. Ожидание восстановления (без рестарта)...
     ❤️ Пульс восстановлен после 19 сбоев.
     ```
   - **Анализ:** Авария локального интернет-соединения/сетевой карты длилась ~20 минут. Watchdog отработал идеально: бот перешел в режим ожидания, не ушел в циклический рестарт-луп, сохранил состояние очередей и в 17:52 мгновенно возобновил работу.

3. **Фатальные падения и дедлоки:**
   - `logs/bot_fatal_crash.log`: 0 фатальных сбоев (только плановые `FATAL CRASH WATCH ARMED`).
   - `logs/bot_deadlock_watchdog.log`: 0 записей (дедлоков не было).
   - `media_processor.log`: без новых записей.

---

## 2. АУДИТ ПРЕДУПРЕЖДЕНИЙ И ВНЕШНИХ СЕРВИСОВ

### 2.1. Telegram Bot API
1. **FloodWait:**
   - **Количество:** 9 событий по 30.0s.
   - **Участники:** Боты пула `7823520763`, `8384397544`, `8102947050` во время вечерних пиков рассылки (18:51 - 19:35).
   - **Оценка:** Штатное поведение `BotPool`, боты корректно уходят на 30-секундный кулдаун без потери сообщений.
2. **Ошибки доступа к каналу архива:**
   - **Лог:** `⚠️ [Archive] Bot 8330160701 cannot access channel -1003614166511 (Telegram server says - Bad Request: chat not found)` (4 раза).
   - **Причина:** Боты `8330160701` и `8217841121` из пула архива не добавлены администраторами в канал `-1003614166511`.
3. **[АНОМАЛИЯ] Авария рассылки поста #523156 (задержка 8158 секунд / 2.26 часа):**
   - **Предупреждения в логах:**
     - `738x`: `⚠️ [BROKEN_FILE_ID/MEDIA_INVALID] Auto-downloading media buffer for user <UID>: Telegram server says - Bad Request: wrong remote file identifier specified: can't unserialize it. Wrong last symbol`
     - `126x`: `⚠️ [BROKEN_FILE_ID/MEDIA_INVALID] Auto-downloading media buffer for user <UID>: Telegram server says - Bad Request: wrong file identifier/HTTP URL specified`
     - `373x`: `⚠️ BadRequest отправки user <UID>: Telegram server says - Bad Request: failed to send message #1 with the error message "MEDIA_INVALID". Attempting plain fallback...`
     - `217x`: `delivery_recipient_timeout {"board_id":"sex","post_num":523156,"phase":"passive","uid":...,"timeout_sec":20.0}`
   - **Судебный анализ первопричины:**
     - Пост #523156 в доске `/sex/` содержал медиа-группу из 10 элементов.
     - При сохранении/кэшировании несериализуемых объектов `BufferedInputFile` метод `_json_serializer` в `common/database.py` (строка 93) превратил объекты в строковые литералы:
       `{"type": "photo", "media": "<объект файла: file.png>"}`.
     - `broadcaster.py` получил эти строки в качестве `media_src` и передал их в Telegram API.
     - Telegram отклонил их как невалидный file_id (`unserialize error`).
     - Для каждого из 269 пользователей доски бот пытался скачать `"<объект файла...>"` как URL, падал на таймаут 20 секунд и пытался отправить текстовый fallback.
     - Общее время рассылки одного поста составило **8158.4 секунды (2.26 часа)**.

---

### 2.2. AI-провайдеры (Gemini, Groq, OpenRouter)

| Провайдер | Модель | Успешно (200 OK) | 429 Too Many Requests | 503 Unavailable / 413 Too Large | Ошибки авторизации (401) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Google Gemini** | `gemini-3.1-flash-lite` | **306** | 15 | 14 (503) | 0 |
| **Google Gemini** | `gemini-openai-compat` | **221** | 10 | 0 | 0 |
| **Google Gemini** | `gemini-2.5-flash` | **163** | **148** | 5 (503) | 0 |
| **Google Gemini** | `gemini-3.5-flash-lite` | **105** | 1 | 0 | 0 |
| **Groq API** | `qwen/qwen3.8-27b`, `qwen3.6` | 280+ | 2 | 21 (413 Payload Too Large) | **7 (100% пула)** |
| **OpenRouter** | — | 0 | 0 | 0 | 0 |

1. **Google Gemini:**
   - Ключ `AQ.Ab8RN...` в теггере зрения систематически упирается в Rate Limit (164 раза штрафовался на 120s кулдаун).
   - Модель `gemini-3.1-flash-lite` периодически возвращает 503 (14 раз), после чего ротатор переключается на рабочие модели.
2. **[КРИТИЧЕСКАЯ ПРОБЛЕМА] Полное аннулирование пула Groq:**
   - В период `18:22:53` — `18:23:09` ВСЕ 7 API-ключей Groq из `.env` вернули `401 Unauthorized`:
     `❌ groq key gsk_... is unauthorized (401). Removing from pool.`
   - В текущий момент в `groq_pool` осталось **0 активных токенов**. Весь функционал Groq отключен до обновления токенов.

---

### 2.3. Edge-TTS и речевой синтез
- Всего за 24 часа: 9 событий в `common.tts_engine`.
- 7 раз возникал таймаут первого коннекта (`Edge-TTS attempt 1 timed out`), после чего ретрай проходил успешно.
- 2 раза произошел полный сбой Edge-TTS (в 20:47:23 TimeoutError и в 18:57:17 NoAudioReceived). В обоих случаях бот **бесшовно переключился на резервный Google TTS (`gTTS`)**, аудио-роасты были успешно сгенерированы и доставлены.

---

## 3. СОСТОЯНИЕ СИСТЕМНЫХ МЕТРИК

### 3.1. Память (Private Memory)
- **Минимум:** 859.38 MB (сразу после старта процесса)
- **Максимум:** 1361.99 MB
- **Текущее:** 1356.63 MB
- **Динамика:** Память растет в первые 3-4 часа работы до момента заполнения кольцевого кэша `BOT_COPY_CACHE_POST_LIMIT = 400` (~265k элементов в `message_to_post` при рассылке на 700 пользователей), после чего держится стабильно в коридоре 1300–1360 MB.
- **Вердикт:** **Утечек памяти нет.** `auto_memory_cleaner` и сборщик мусора GC отрабатывают штатно (`GC объектов собрано: 2020..10312`).

### 3.2. SQLite WAL
- **Минимум:** 0.00 MB
- **Максимум:** 6.92 MB
- **Текущее:** 6.16 MB
- **Вердикт:** **Раздувание WAL отсутствует.** Воркер `wal_checkpoint` каждые 10 минут выполняет PASSIVE чекпоинт, удерживая журнал строго до 7 MB.

### 3.3. Очереди сообщений
- **Пик:** 26 очередей (при одновременном залпе постов)
- **Текущее:** 0 очередей
- **Вердикт:** Зависших очередей нет, все доски полностью разгружены.

---

## 4. ТОП-ПРОБЛЕМЫ И РЕКОМЕНДАЦИИ

| Приоритет | Компонент | Проблема | Статус / Готовый фикс |
| :---: | :--- | :--- | :--- |
| **P0** | `delivery_manager.py` | `NameError: name 'os' is not defined` в `board_help_worker` (строка 1369) | **Исправлено в коде.** Добавлен `import os`. |
| **P0** | `.env` / `common/token_pool.py` | Все 7 ключей Groq заблокированы (`401 Unauthorized`), Groq-пул пуст. | **Требуется действие:** Заменить ключи `GROQ_API_KEYS` в `.env`. |
| **P1** | `broadcaster.py` | Зависание рассылки на 2+ часа при появлении невалидных `file_id` (например, `"<объект файла: ...>"`) | Добавить валидацию `media_src` и fallback на текст в `broadcaster.py`. |
| **P1** | `common/database.py` | `_json_serializer` сохраняет `BufferedInputFile` как псевдо-file_id `"<объект файла: ...>"`. | Заменять несериализуемые файлы на `None` или вырезать их из медиагруппы при дампе. |
| **P2** | Telegram Archive | Боты `8330160701` и `8217841121` получают `chat not found` в канале `-1003614166511`. | Добавить обоих ботов в администраторы канала архива. |
| **P2** | Google Gemini Pool | Ключ `AQ.Ab8RN...` перегружен запросами теггера (164x 429). | Добавить cooldown/staggering в `site_tgach/vision.py` при теггинге. |
