# dvachbot / tgach.top — Project Agent Rules

**Stack:** Python 3.11+, asyncio, aiogram 2.x/3.x, aiosqlite WAL, FastAPI/aiohttp (site_tgach), multimodal LLM cascade (Groq + Gemini).  
**DB:** `dvach_bot.db` (WAL mode). Конфиг: `common/config.py`. Корень: `C:\Users\danat\Desktop\dvachbot`

Эти правила переопределяют / расширяют глобальный `AGENTS.md` для этого проекта.

---

## 1. АРХИТЕКТУРА — LAYOUT МОДУЛЕЙ (КАНОНИЧЕСКИЙ)

### Бот-ядро (корень)
| Файл | Ответственность |
|------|----------------|
| `main.py` (~1.5 MB) | **ВСЕ** хэндлеры Telegram: `/rob`, `/shit`, `/curse`, `/shoot`, `/partyvan`, `/wardrobe`, `/inventory`, `/passport`, `/me`, `/pay`, `/casino`, `/lootbox` и 100+ других |
| `summarize.py` | **Главный LLM cascade** — Groq + Gemini. `GROQ_CONFIG`, `_PERSONA_SEMAPHORE`, `_key_cooldowns`, `_provider_cooldowns`, `get_shared_http_client()`. НЕ путать с `site_tgach/` |
| `shared_state.py` | Глобальное async-состояние. Мутации — только через `asyncio.Lock` |
| `wardrobe_engine.py` | Экипировка, сет-бонусы, `get_wardrobe_total_stats()` с TTL и durability |
| `combat_moderation_engine.py` | `calculate_combat_duration_and_backfire()`, mute, backfire |
| `lootbox_engine.py` | `roll_trash_lootbox()`, `roll_gold_safe()`, `roll_whale_safe()`, дроп-таблицы, RTP, cashback |
| `whale_economy_engine.py` | Whale safes, `/raid_oligarch`, wealth tax |
| `auction_engine.py` | `place_auction_bid()` — атомарный escrow, refund, anti-sniping |
| `bank_engine.py` | Банковские операции |
| `market_engine.py` | P2P-рынок |
| `economy_extension.py` | Расширение экономики |
| `post_helpers.py` | `format_header()`, `format_thread_post_header()` — форматирование постов/тредов |

### Common (общие модули)
| Файл | Ответственность |
|------|----------------|
| `common/database.py` (~460 KB, 10k строк) | **Весь SQL-слой**: `initialize_database()`, все CRUD-функции, миграции, FTS, индексы |
| `common/db_pool.py` | `get_pool()`, `db_lock`, `db_transaction`, `safe_begin_immediate()`, `safe_commit()`, `safe_rollback()` |
| `common/config.py` | `DB_NAME`, `ADMIN_IDS`, `SITE_PUBLIC_BASE_URL`, `STORAGE_CHANNELS`, все BOT_* константы из `.env` |
| `common/token_pool.py` | `groq_pool`, `google_pool` — ротация API-ключей |
| `common/bot_pool.py` | `global_bot_pool` — пул Telegram-ботов |
| `common/spam_filter.py` | Антиспам |
| `common/work_engine.py` (~140 KB) | `execute_job_action()`, job shifts, lootbox drops, fines |
| `common/text_utils.py` | `clean_ai_thinking()`, `strip_thinking_tags()` |
| `handlers/message_router.py` | Роутер входящих сообщений |

### site_tgach/ (сайт — ОТДЕЛЬНЫЙ ДОМЕН)
| Файл | Ответственность |
|------|----------------|
| `site_tgach/main.py` | FastAPI/aiohttp-сервер сайта tgach.top |
| `site_tgach/vision.py` | Vision cascade — тэггинг изображений |
| `site_tgach/neuro_moderator.py` | `GROQ_MODELS = ["qwen/qwen3.8-27b"]`, `run_deep_check()`, авто-цензура |
| `site_tgach/neuro_poster.py` | `_execute_groq_post()`, генерация постов |
| `site_tgach/tagging_worker.py` | Фоновый worker тэггинга, `GROQ_MODEL` single |
| `site_tgach/importer.py` | Импорт постов с 2ch |
| `site_tgach/security.py` | PoW, IP-бан, rate limiting |
| `site_tgach/admin_config.py` | `ADMIN_IDS`, `IP_BAN_LIST` |

**КРИТИЧЕСКИ:** `site_tgach/` и бот — **два разных домена**. Не смешивать модели, DB-функции, конфиги.

---

## 2. LLM — МОДЕЛИ И API КЛЮЧИ

### Текущие модели в коде (читай перед правкой!)
- `summarize.py` → `GROQ_CONFIG["model"] = "qwen/qwen3.8-27b"` (Groq)
- `site_tgach/neuro_moderator.py` → `GROQ_MODELS = ["qwen/qwen3.8-27b"]`
- `common/token_pool.py` → `groq_pool`, `google_pool` (ротация ключей)

### Groq-модели
| Статус | Модель |
|--------|--------|
| ✅ Production | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b` |
| ⚠️ Preview (живые!) | `qwen/qwen3.8-27b`, `qwen/qwen3.6-27b` — НЕ ТРОГАТЬ без проверки |
| ❌ Dead | `llama-3.2-90b-vision-preview`, `qwen-2.5-32b` |

### Gemini-модели
| Лимит | Модель |
|-------|--------|
| 15 RPM | `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` |
| 5–10 RPM | `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |

### Различай HTTP-ошибки LLM:
- `400 "has been decommissioned"` → модель мёртвая → убрать из конфига
- `429 Too Many Requests` → rate limit, модель ЖИВАЯ → **НЕ УДАЛЯТЬ**
- `403 "Your project has been denied access"` → API KEY забанен (не модель!) → убрать из `.env GOOGLE_API_KEYS`

### Файлы с конфигами моделей:
```
summarize.py              — GROQ_CONFIG, google cascade
site_tgach/vision.py      — vision cascade
site_tgach/neuro_moderator.py — GROQ_MODELS list
site_tgach/tagging_worker.py  — GROQ_MODEL single
site_tgach/neuro_poster.py    — inline model calls
.env / .envgoogle         — GOOGLE_API_KEYS (comma-separated)
common/token_pool.py      — groq_pool, google_pool ротация
```

**Перед изменением model-конфигов:** `git log --oneline -20`

### Semaphore-логика (критично!):
В `summarize.py` есть `_PERSONA_SEMAPHORE = asyncio.Semaphore(1)` — ограничение до 1 параллельного LLM-вызова персоны. Это **намеренно** — защита от спама 429. Не убирать без понимания последствий.

---

## 3. DATABASE (aiosqlite WAL)

**Главный файл:** `common/database.py` — 10133 строк, 460 KB. Читать только нужный участок.

### Транзакционные примитивы (из `common/db_pool.py`):
```python
db_transaction       # contextmanager: BEGIN IMMEDIATE → COMMIT/ROLLBACK
safe_begin_immediate # ручной BEGIN IMMEDIATE с retry
safe_commit          # COMMIT с обработкой ошибок
safe_rollback        # ROLLBACK безопасный
db_lock              # asyncio.Lock для сериализации записи
get_pool()           # получить aiosqlite connection pool
```

### Правила:
1. **Atomic transactions обязательны:** Любая мутация нескольких таблиц (баланс + инвентарь + лог) — только через `db_transaction`. Bare SQL вне транзакции при записи — запрещено.
2. **WAL-специфика:** Конкурентное чтение ✅, серийная запись через `db_lock` ✅. Не использовать `EXCLUSIVE` lock без нужды.
3. **Никогда не писать напрямую** в `dvach_bot.db` из скриптов-разведчиков — только через официальные функции `common/database.py`.
4. **Soft overdraft:** При дефиците баланса/склада — предупреждение, не краш транзакции. Пользователь не должен попадать в тупик.
5. **Schema changes:** Только через миграционный скрипт внутри `initialize_database()`. Никаких прямых `ALTER TABLE` в REPL/scratch.
6. **Индексы:** `user_id`, `created_at`, `chat_id` в горячих запросах — обязан быть индекс. Проверять через `EXPLAIN QUERY PLAN`.
7. **SQLite LIMIT:** `SQLITE_LIMIT_VARIABLE_NUMBER` = 32766. При `IN (?, ...)` с > 500 параметров — чанкуй (это уже закодировано в database.py).

---

## 4. ASYNCIO & AIOGRAM SAFETY

1. **Blocking calls в async-хэндлерах — запрещены:** Нет `time.sleep()`, нет синхронного `requests`. Только `asyncio.sleep()`, `aiohttp`, `httpx.AsyncClient`.
2. **`get_shared_http_client()`** в `summarize.py` — переиспользуй, не создавай новые `AsyncClient` в каждом вызове.
3. **Rate limit aiogram:** Обрабатывай `RetryAfter`, `BotBlocked`, `ChatNotFound`, `MessageNotModified` — не давать краш-loop.
4. **Timeouts обязательны:** HTTP-вызовы к LLM: дефолт 60s (`summarize.py`), `GROQ_TIMEOUT = 45.0` (`neuro_moderator.py`). Не убирать.
5. **Semaphore anti-spam:** `_PERSONA_SEMAPHORE(1)` — лимит конкурентных LLM-вызовов. Расширять только с обоснованием.
6. **shared_state.py мутации:** Только через `asyncio.Lock`. Никаких гонок при записи.
7. **task_manager.py:** `spawn_task()` — для fire-and-forget coroutines. Использовать вместо голого `asyncio.create_task()`.

---

## 5. VPN / GEO-ЛОГИКА (КУКА `user_country`)

**3 независимых механизма — не смешивать и не путать:**

| Механизм | localStorage key | Тригер | Частота |
|----------|-----------------|--------|---------|
| `welcome-modal` | `welcome_v5` | Первый вход | Один раз |
| Toast-алерт | `ru_vpn_alert_shown` | `/api/is-ru` → RU | Раз в 24ч |
| `VpnManager` | `vpn_disclaimer_ts` | Кука `user_country=RU` | Каждые 12ч |

**ЗАКОН:** Кука `user_country` ОБЯЗАНА быть `httponly=False`. Если поставить `httponly=True` — JS-логика `VpnManager` её не увидит, гео-фильтры сломаются, пользователи из RU не получат VPN-инструкцию.

**Источник гео-данных:** `site_tgach/` использует `GeoLite2-Country.mmdb` (MaxMind GeoIP2) через соответствующую библиотеку.

---

## 6. МАТЕМАТИКА ЭКОНОМИКИ (RTP / EV ЗАКОНЫ)

**Критический инвариант.** Нарушение = поломка баланса игры на продакшн.

| Механика | Лимит / Формула |
|----------|----------------|
| Trash Lootbox RTP | ≤ 85% (target ~52.8%), Cash EV ~25.32 ₪ |
| Gold Safe RTP | ≤ 85% (target ~62.1%), Cash EV ~113.80 ₪ |
| Whale Safe RTP | ≤ 65% |
| Duplicate cashback | `min(case_price * 0.30, item_price * 0.20)` |
| Whale burn to Abu Fund | 70% обязательно |
| Whale Safe цена | `50000 × 1.5^n` (где n = open_count_today) |

**Запрещено** изменять дроп-таблицы (`TRASH_ITEMS`, `PREMIUM_JUNK`) без пересчёта EV и прогона Monte-Carlo (≥ 5000 итераций) через `tests/test_lootbox_rebalance.py`.

---

## 7. ТЕСТ-ИНФРАСТРУКТУРА

**Тест-сьют — ~140 файлов в `tests/`.** Изолирован от продакшн-DB.

### Правила тестирования:
1. **Изолированная DB:** Все тесты используют `isolated_test_db` из `tests/conftest.py`. Попытка подключиться к `dvach_bot.db` → `RuntimeError`. Никогда не трогать продакшн-БД из тестов.
2. **Targeted runs:** Не гони весь сьют на локальную правку:
   ```bash
   .\venv\Scripts\python.exe -m pytest tests/test_wardrobe_combat_utility.py -v
   .\venv\Scripts\python.exe -m pytest tests/test_lootbox_rebalance.py -v
   .\venv\Scripts\python.exe -m pytest tests/test_whale_money_sinks.py -v
   ```
3. **Таймауты:** ≤ 10s unit, ≤ 60s suite. `--timeout=10` через `pytest-timeout`.
4. **Telegram API мокирован** на уровне сокетов — никаких реальных запросов к `api.telegram.org` в тестах.
5. **Monte-Carlo:** ≥ 5000 итераций для стохастических RTP-тестов.
6. **Deterministic seeds:** Стохастические тесты используют фиксированные seeds или BVA (law of large numbers, N ≥ 5000).
7. **WAL concurrency** (`test_whale_money_sinks.py`) — проверяй deadlock-safety параллельных транзакций.

### Ключевые тест-файлы:
```
tests/test_wardrobe_combat_utility.py  — wardrobe stats, combat formulas
tests/test_lootbox_rebalance.py       — drop tables, RTP Monte-Carlo
tests/test_whale_money_sinks.py       — whale safes, auctions, WAL concurrency
tests/test_m1_econ_engines.py         — economy engines
tests/test_main.py                    — command handlers integration
tests/test_summarize.py               — LLM cascade
tests/test_vision_cascade.py          — vision pipeline
```

---

## 8. SECURITY

1. **Секреты только в `.env` / `.envgoogle`.** `BOT_TOKEN`, `GOOGLE_API_KEYS`, `GROQ_API_KEY`, `ADMINS` — только env. В коде — никогда.
2. **`ADMIN_IDS`** берётся из `common/config.py` → `os.getenv("ADMINS")`. Хардкодить user_id где-либо ещё — запрещено.
3. **SQL injection:** Только параметризованные запросы (`?` placeholders). Конкатенация SQL-строк — запрещена.
4. **`site_tgach/security.py`:** PoW (Proof of Work), IP-бан — `IP_BAN_LIST` из `site_tgach/admin_config.py`.
5. **SSRF-защита:** В `site_tgach/` — валидация URL перед fetch (защита от AWS metadata endpoint `169.254.169.254`).
6. **Media processing:** Проверяй размеры перед обработкой — decompression bomb (50000×50000px). `site_tgach/image_processing.py` имеет protection.
7. **`common/secret_redaction.py`:** Использовать для очистки секретов из логов.
8. **`SECURITY.md`** в корне — читай перед правками auth/admin-логики.

---

## 9. SITE_TGACH / STOMCHAT СПЕЦИФИКА

**site_tgach/ — полностью отдельный веб-домен.** Не импортировать напрямую из бот-кода и наоборот (кроме `common/`).

### Ключевые компоненты:
- **`site_tgach/importer.py` (~53 KB)** — импорт постов с 2ch. Сложная логика, читать полностью перед правкой.
- **`site_tgach/tagging_worker.py` (~65 KB)** — фоновый worker. `TAGGING_PROMPT` определён в `neuro_moderator.py` и импортируется сюда.
- **`site_tgach/vision.py` (~35 KB)** — vision cascade с multi-model fallback.
- **`site_tgach/neuro_poster.py` (~36 KB)** — автопостинг с LLM.
- **`site_tgach/mirror_worker.py`** — зеркалирование контента.
- **`site_tgach/mtproto_client.py`** — MTProto для Telegram-интеграции сайта.

### Правила site_tgach:
1. **`TAGGING_PROMPT`** в `neuro_moderator.py` — канонический источник. Tagging_worker.py импортирует его оттуда. Не дублировать.
2. **`vision.py` GROQ_MODELS** — vision-модели ОБЯЗАНЫ поддерживать vision (multimodal). Не подставлять text-only модели.
3. **Freeimage, Catbox, Pixhost, Imgbb** (`site_tgach/*.py`) — разные CDN-хосты для медиа. Каждый со своей логикой retry и таймаутов.
4. **GeoLite2-Country.mmdb** (`site_tgach/`) — большой бинарный файл (9.6 MB). Не трогать, не заменять без обновления с MaxMind.
5. **`hf_batcher.py`** — HuggingFace inference batching. Изолировать от основного event loop.

---

## 10. ЗАПРЕЩЕНО В ЭТОМ ПРОЕКТЕ

- ❌ Удалять/деактивировать LLM-модели по `429` ошибке — это rate limit, не смерть модели
- ❌ Тестировать API-ключи параллельными запросами без пауз — бан аккаунта
- ❌ Класть scratch-скрипты в корень dvachbot — только `<appDataDir>/brain/<id>/scratch/`
- ❌ `git add .` без diff-аудита
- ❌ Синхронные blocking calls в async-хэндлерах (`time.sleep`, `requests.get`)
- ❌ Изменять дроп-таблицы без Monte-Carlo верификации RTP
- ❌ Хардкодить `user_id` администраторов вне `common/config.py` / `.env`
- ❌ Писать напрямую в `dvach_bot.db` из скриптов-разведчиков
- ❌ Смешивать `site_tgach/` и бот-ядро напрямую (только через `common/`)
- ❌ Убирать `_PERSONA_SEMAPHORE` или увеличивать лимит без понимания 429-последствий
- ❌ Ставить `httponly=True` на куку `user_country`
- ❌ Запускать весь тест-сьют (140 файлов) для верификации одного локального изменения
