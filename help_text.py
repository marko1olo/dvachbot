# help_text.py
import random

# ============================================================================
# ⚡ МНОГОУРОВНЕВЫЙ ИНТЕРАКТИВНЫЙ СПРАВОЧНЫЙ ЦЕНТР ТГАЧ (HELP HUB)
# ============================================================================

HELP_HUB_PAGES_RU = {
    "main": (
        "⚡ <b>Справочный Центр ТГАЧ /b/</b>\n\n"
        "Добро пожаловать в анонимную борду! Здесь нет цензуры, но есть свои правила и законы.\n\n"
        "💡 <i>Выбери нужный раздел на цветных кнопках ниже:</i>\n\n"
        "• 💬 <b>Общение</b> — Как постить, отвечать, шептать и удалять посты\n"
        "• 💰 <b>Экономика</b> — Шекели, кошелек, работа, рынок и топ богачей\n"
        "• 🖼 <b>Медиа & Демы</b> — Демотиваторы, постеры с QR, хентай и роллы\n"
        "• 🧠 <b>ИИ & Аналитика</b> — Саммари чата, прожарка треда и теги\n"
        "• 🎭 <b>Шизо-Режимы</b> — 15+ стилей общения на 5 минут\n"
        "• ⚔️ <b>Разборки</b> — Ограбления, дуэли, говно, проклятия и пативэн\n"
        "• ⚙️ <b>Настройки</b> — Спойлеры на NSFW, фильтры слов и API\n"
        "• 📋 <b>Все команды</b> — Полный алфавитный справочник\n"
        "• 🌐 <b>Борды & Каналы</b> — Все живые доски, каналы, сайт и техподдержка\n\n"
        "🌐 Сайт: <a href=\"https://tgach.top\">tgach.top</a> | Канал: <a href=\"https://t.me/tgach_bot\">t.me/tgach_bot</a> | Архив: <a href=\"https://t.me/tgchan_archive\">t.me/tgchan_archive</a>"
    ),
    "chat": (
        "💬 <b>Раздел: Общение и Постинг</b>\n\n"
        "• <b>Как написать пост:</b> Просто отправь любой текст, фото, стикер, видео или голосовое боту — оно мгновенно появится на доске под анонимным номером.\n\n"
        "• <b>Как ответить анону:</b> Сделай <b>Reply (Ответить)</b> на сообщение в чате. Автор получит анонимное уведомление о реплае.\n\n"
        "• <b>Эмодзи-реакции:</b>\n"
        "  👍 <b>Лайк / База:</b> Начисляет автору <b>+12.0 ₽</b>\n"
        "  👎 <b>Сажа / Дизлайк:</b> Списывает у автора штраф <b>-5.5 ₽</b>\n"
        "  🤡, 😱, 🤔, 🤣 — Другие эмодзи отправляют автору анонимную цитату с двачевским подколом.\n\n"
        "• <code>/redact</code> — Удалить свой последний пост (отправь реплаем на него).\n"
        "• <code>/whisper &lt;текст&gt;</code> — Отправить тайный анонимный шёпот автору поста.\n"
        "• <code>/poll Тема | Вариант 1 | Вариант 2</code> — Создать анонимное голосование.\n"
        "• <code>/report</code> — Отправить жалобу модераторам на спам, ЦП или вайп."
    ),
    "economy": (
        "💰 <b>Раздел: Экономика, Казино и Шекели</b>\n\n"
        "Шекели (₪) — главная валюта борды для прокачки, покупок и казино:\n\n"
        "• <code>/wallet</code> — Кошелек, баланс, история операций и рефералы\n"
        "• <code>/bank</code> (<code>/deposit</code>, <code>/withdraw</code>) — <b>Банк Абу и Сейф:</b> 100% защита от /rob, вклады под процент (0.5% - 6.0%/день)\n"
        "• <code>/market</code> (<code>/bazar</code>, <code>/sell</code>) — <b>P2P Барахолка:</b> Торговля шмотом, оружием и кейсами между анонами\n"
        "• <code>/shop</code> — <b>Торговый Хаб:</b> Оружие, Бутик, Аптека (Ксива полковника, Удостоверение дружинника, Взятки), Кейсы\n"
        "• <code>/work</code> — Биржа труда: 15 вакансий со сбором сетов и лута\n"
        "• <code>/casino</code> — Казино: <code>/slots</code>, <code>/coinflip</code>, <code>/blackjack</code>, <code>/rroulette</code>, <code>/ttt</code>, <code>/dice_duel</code>, <code>/duel_rr</code>\n"
        "• <code>/ttt &lt;ставка&gt;</code> — ❌⭕ Крестики-Нолики PvP на шекели (таймер 60 сек)\n"
        "• <code>/dice_duel &lt;ставка&gt;</code> — 🎲 PvP Дайс-Дуэль 2d6 на шекели (честный генератор ⚀⚁⚂⚃⚄⚅)\n"
        "• <code>/duel_rr &lt;ставка&gt;</code> — 💀 Русская Рулетка PvP (6 камор, 1 патрон, проигравшему мут 30 мин)\n"
        "• <code>/lootbox</code> — Кейсы: Мусорный пакет (150₪) и Золотой сейф (500₪)\n"
        "• <code>/avatar</code> — Карточка персонажа RPG и гардероб экипировки\n"
        "• <code>/ach</code> — Зал достижений (12 трофеев с выплатой шекелей)\n"
        "• <code>/drop &lt;сумма&gt;</code> — Сбросить пачку шекелей в тред на реакцию\n"
        "• <code>/daily</code> — Ежедневный бонус (+75 ₪ + стрик)\n"
        "• <code>/gtop</code> — Список самых богатых китов борды"
    ),
    "media": (
        "🖼 <b>Раздел: Медиа, Инвайты и Демотиваторы</b>\n\n"
        "• <code>/dem Заголовок | Подпись</code> — <b>Генератор демотиваторов!</b> Ответь реплаем на любое фото/картинку, и бот соберёт каноничный постер с чёрной рамкой и шрифтом Impact.\n"
        "• <code>/invite_pic</code> — Сгенерировать стильный постер с QR-кодом для вербовки друзей (7 визуальных стилей: Киберпанк, Демотиватор, Матрица, Аниме, Вейпорвейв и др.).\n"
        "• <code>/invite</code> — Получить порцию отборных текстовых фраз для зазыва анонов.\n"
        "• <code>/fap</code> (<code>/hent</code>, <code>/nsfw</code>) [число] — Случайный аниме/хентай арт (можно писать <code>/fap 5</code> для пака из 5 штук).\n"
        "• <code>/loli</code> [число] — Лоликон-арт (безопасный/этти).\n"
        "• <code>/roll</code> (<code>/dice</code>, <code>/рулетка</code>) — Бросить кубик удачи от 0 до 100.\n"
        "• <code>/ruletka</code> — Перейти в случайный тред борды."
    ),
    "ai": (
        "🧠 <b>Раздел: Нейросети, Аналитика & Постеры</b>\n\n"
        "• <code>/stats_hub</code> (<code>/пульс</code>, <code>/deck</code>) — <b>Главный пульт аналитики!</b> Мгновенный пульс со спарклайнами, инлайн-меню постеров и ссылка на WebApp.\n"
        "• <code>/my_wrapped</code> (<code>/wrapped</code>, <code>/паспорт</code>) — <b>Персональный 2ch Wrapped:</b> HD-постер с архетипом личности, хронотипом, спарринг-партнерами и диагнозом ИИ.\n"
        "• <code>/economy_stats</code> (<code>/econ</code>, <code>/казна</code>) — HD-срез теневой экономики, казино и грабежей.\n"
        "• <code>/pvp_stats</code> (<code>/война</code>, <code>/пвп</code>) — HD-срез войн дебаффов, метания говна и брони фольги.\n"
        "• <code>/drama_stats</code> (<code>/бифы</code>, <code>/враги</code>) — HD-карта заклятых врагов, токсичности досок и ночного психоза.\n"
        "• <code>/memes_stats</code> (<code>/баян</code>, <code>/мемы</code>) — HD-баянометр вирусных мемов, AI-тегов и сленга.\n"
        "• <code>/passport</code> (<code>/me</code>) — Паспорт Тгачера с рангом, балансом и экипировкой.\n"
        "• <code>/dossier</code> (<code>/досье</code>) — Личное дело анона из картотеки КГБ.\n"
        "• <code>/summarize</code> (<code>/саммари</code>) — ИИ анализирует последние 50 постов треда и выдает суть.\n"
        "• <code>/roast</code> (<code>/прожарка</code>) — Жёсткая нейросетевая прожарка атмосферы борды.\n"
        "• <code>/stats</code> — Графики активности доски.\n"
        "• <code>/tags</code> — Облако ключевых тем и популярных слов за сутки."
    ),
    "modes": (
        "🎭 <b>Раздел: Шизо-Режимы Общения (на 5 минут)</b>\n\n"
        "Активация режима меняет стиль и лексику всех твоих постов на 5 минут:\n\n"
        "• 🌸 <code>/anime</code> — Няшный они-чан с кавайными вздохами\n"
        "• 🇷🇺 <code>/zaputin</code> — Патриотический Z-режим, ГОЙДА и скрепы\n"
        "• 🇺🇦 <code>/slavaukraine</code> — Шаровары, перемога и хуторской диалект\n"
        "• ⚔️ <code>/warhammer</code> — Инквизиция, слава Омниссии и еретики\n"
        "• 📜 <code>/imperial</code> — Дореволюционный слог с ятями и сударями\n"
        "• 👊 <code>/gopnik</code> — Семки, кенты, мобилы и базар по понятиям\n"
        "• 🧠 <code>/schizo</code> — Теории заговора, рептилоиды и галоперидол\n"
        "• 🇵🇱 <code>/polish</code> — Пше-пше, курва я пердоле\n"
        "• 🐊 <code>/rus</code> — Древнерусские русы против ящеров\n"
        "• 🐒 <code>/abu</code> — Суржик создателя всея Двача\n"
        "• 🕶 <code>/matrix</code> — Избранный Нео и зеленый терминал\n"
        "• 📟 <code>/oldweb</code> — Эпоха модемов 56k, Web 1.0 и FIDO\n"
        "• ✡️ <code>/jewish</code> — Таки гешефт, маца и кошерный бизнес\n"
        "• 🦅 <code>/america</code> — Freedom, капитализм и бургеры"
    ),
    "actions": (
        "⚔️ <b>Раздел: Разборки и Интерактив</b>\n\n"
        "Все эти команды применяются <b>ответом (Reply)</b> на пост неугодного анона:\n\n"
        "• <code>/dossier</code> — Запросить Личное Дело на автора поста из картотеки.\n"
        "• <code>/rob</code> — Ограбление! Шанс украсть 10-30% шекелей с баланса жертвы.\n"
        "• <code>/shit</code> — Запустить свежим говном в автора поста.\n"
        "• <code>/curse</code> — Наложить проклятие: следующие посты жертвы будут искажаться шизо-стилем.\n"
        "• <code>/partyvan</code> — Вызвать пативэн с мигалками и отправить анона в КПЗ.\n"
        "• <code>/duel &lt;сумма&gt;</code> — Бросить перчатку и сойтись в перестрелке на деньги.\n"
        "• <code>/ttt &lt;сумма&gt;</code> — Вызвать на дуэль в Крестики-Нолики 3x3 на шекели (таймер 60 сек).\n"
        "• <code>/dice_duel &lt;сумма&gt;</code> — Вызвать на бросок костей 2d6 на шекели (⚀⚁⚂⚃⚄⚅).\n"
        "• <code>/duel_rr &lt;сумма&gt;</code> — Вызвать на Русскую Рулетку PvP на шекели (проигравшему мут 30 мин).\n"
        "• <code>/deanon</code> — Шуточный спуфинг-деанон с генерацией фейкового IP и адреса.\n"
        "• 🗳️ <code>/votemute</code> — <b>Народный Вотум / Шизо-Мут:</b> Выдвинуть пост нарушителя на голосование. 5 голосов анонов за 10 минут отправляют шиза в <b>ЖЕЛЕЗНЫЙ МУТ на 30 минут</b> (не продается за взятки в /shop!).\n"
        "• 📋 <code>/dopros</code> (<code>/допрос</code>) — <b>Вызов на допрос в Отдел «К»</b> (себе или реплаем). Дай взятку 50₪, возьми 51-ю статью или сдай соседа по борде!\n"
        "• 🪪 <code>/fine</code> (<code>/штраф</code>, <code>/druzhina</code>) — <b>Штраф от Дружинника (Reply)</b>. Требует «Удостоверение дружинника» из /shop. Штрафует нарушителя на 15 ₪ (10 ₪ дружиннику, 5 ₪ в Фонд Абу) раз в сутки."
    ),
    "settings": (
        "⚙️ <b>Раздел: Настройки и Управление</b>\n\n"
        "• <code>/nsfw</code> — Переключить авто-спойлер на все входящие медиафайлы (безопасно для учебы/работы).\n"
        "• <code>/hide &lt;слово&gt;</code> — Добавить слово в персональный черный список (посты с ним скроются).\n"
        "• <code>/togglegif</code> — Скрыть тяжелые GIF-анимации для экономии трафика.\n"
        "• <code>/token</code> — Получить персональный ключ авторизации для Web-интерфейса ТГАЧ.\n"
        "• <code>/admin</code> — Панель модератора борды (только для администрации)."
    ),
    "all": (
        "📋 <b>Полный список всех команд ТГАЧ:</b>\n\n"
        "<b>Общение:</b> /start, /help, /redact, /whisper, /poll, /report, /quote, /dice\n"
        "<b>Профиль/Досье:</b> /passport (/me, /я, /паспорт), /my_wrapped (/wrapped), /dossier, /inv\n"
        "<b>Аналитика & Постеры:</b> /stats_hub (/пульс, /deck), /economy_stats (/econ), /pvp_stats (/война), /drama_stats (/бифы), /memes_stats (/баян)\n"
        "<b>Экономика & PvP:</b> /wallet, /bank, /deposit, /withdraw, /market, /sell, /my_lots, /work, /daily, /shop, /top, /duel, /ttt, /dice_duel, /duel_rr, /drop, /casino\n"
        "<b>Медиа:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>ИИ:</b> /summarize, /roast, /stats, /tags\n"
        "<b>Интерактив (Reply):</b> /dossier, /rob, /shit, /curse, /partyvan, /deanon, /votemute, /dopros, /fine\n"
        "<b>Настройки:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>Режимы:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>Доски:</b> /b/, /a/, /po/, /soc/, /sex/, /h/, /bunker/, /vg/, /v/, /tech/, /ai/, /wh40k/, /mu/, /tv/, /fit/, /sci/, /biz/, /news/, /fa/, /x/, /vt/, /au/, /me/, /int/, /meta/, /thread/"
    ),
    "boards": (
        "🌐 <b>Каталог Борд &amp; Каналов ТГАЧ</b>\n\n"
        "Сеть анонимных Telegram-борд и веб-разделов единой экосистемы ТГАЧ!\n\n"
        "🤖 <b>Живые доски прямо в Telegram (боты):</b>\n"
        "• <b>/b/</b> (@dvach_chatbot) - Свободное общение\n"
        "• <b>/a/</b> (@dvach_a_chatbot) - Аниме и Манга\n"
        "• <b>/po/</b> (@dvach_po_chatbot) - Политика и дебаты\n"
        "• <b>/sex/</b> (@dvach_sex_chatbot) - Секс и биопроблемы\n"
        "• <b>/vg/</b> (@dvach_vg_chatbot) - Геймдев и треды видеоигр\n"
        "• <b>/v/</b> (@tgach_v_bot) - Видеоигры и консоли\n"
        "• <b>/tech/</b> (@tgach_tech_bot) - IT, софт и технологии\n"
        "• <b>/ai/</b> (@tgach_ai_bot) - AI &amp; Нейросети\n"
        "• <b>/news/</b> (@tgach_news_bot) - Новости\n"
        "• <b>/int/</b> (@tgchan_chatbot) - International board\n"
        "• <b>/meta/</b> (@tgach_meta_bot) - Работа борды\n"
        "• <b>/thread/</b> (@thread_chatbot) - Каталог и отдельные треды\n\n"
        "🌐 <b>Тематические доски на сайте (<a href=\"https://tgach.top\">tgach.top</a>):</b>\n"
        "• /soc/ (Знакомства), /h/ (Хентай), /bunker/ (Убежище), /fit/ (Фитнес), /me/ (Медицина), /tv/ (Кино/ТВ), /sci/ (Наука), /wh40k/ (Warhammer), /biz/ (Бизнес), /mu/ (Музыка), /fa/ (Мода), /x/ (Мистика), /vt/ (Витьюберы), /au/ (Авто)\n\n"
        "📢 <b>Официальные Telegram-каналы:</b>\n"
        "• <b>Новости &amp; Апдейты:</b> @tgach_bot\n"
        "• <b>Вечный архив тредов:</b> @tgchan_archive\n\n"
        "🌐 <b>Официальный веб-портал:</b>\n"
        "• <a href=\"https://tgach.top\">tgach.top</a> — WebApp, каталог тредов, поиск и Тгач.Радио\n\n"
        "🆘 <b>Техподдержка и связь:</b>\n"
        "• <a href=\"https://t.me/voprosy?start=rba30\">Обратная связь ТГАЧ</a>"
    )
}

HELP_HUB_PAGES_EN = {
    "main": (
        "⚡ <b>TGACH /b/ — Help & Documentation Hub</b>\n\n"
        "Welcome to the anonymous imageboard! Choose a category below using interactive buttons:\n\n"
        "• 💬 <b>Chat</b> — Posting, replying, secret whispers & redaction\n"
        "• 💰 <b>Economy</b> — Shekels, wallet, jobs, shop & richest list\n"
        "• 🖼 <b>Media & Demotivators</b> — Custom /dem creator, QR posters, art\n"
        "• 🧠 <b>AI & Analytics</b> — Summaries, roasts & word clouds\n"
        "• 🎭 <b>Speech Modes</b> — 15+ fun conversational styles\n"
        "• ⚔️ <b>Action & PvP</b> — Robberies, duels, hexes & partyvans\n"
        "• ⚙️ <b>Settings</b> — NSFW filters, word blocklists & API tokens\n"
        "• 📋 <b>All Commands</b> — Complete alphabetized index\n"
        "• 🌐 <b>Boards & Channels</b> — All active boards, TG channels, web & support\n\n"
        "🌐 Web: <a href=\"https://tgach.top\">tgach.top</a> | News: <a href=\"https://t.me/tgach_bot\">t.me/tgach_bot</a> | Archive: <a href=\"https://t.me/tgchan_archive\">t.me/tgchan_archive</a>"
    ),
    "chat": (
        "💬 <b>Section: Chat & Posting</b>\n\n"
        "• <b>Post:</b> Send any text, image, sticker, video — it instantly appears anonymously on the board.\n"
        "• <b>Reply:</b> Simply <b>Reply</b> to any message. Author receives anonymous notification.\n"
        "• <b>Reactions:</b>\n"
        "  👍 <b>Like:</b> Gives author <b>+12.0 RUB</b>\n"
        "  👎 <b>Sage:</b> Imposes penalty <b>-5.5 RUB</b>\n"
        "• <code>/redact</code> — Delete your last post (as reply).\n"
        "• <code>/whisper &lt;text&gt;</code> — Send anonymous whisper to author.\n"
        "• <code>/poll Topic | Opt 1 | Opt 2</code> — Create poll.\n"
        "• <code>/report</code> — Report spam/illegal content."
    ),
    "economy": (
        "💰 <b>Section: Economy & Shekels</b>\n\n"
        "• <code>/wallet</code> — Balance & transaction history.\n"
        "• <code>/work</code> (<code>/earn</code>) — Earn cash (recycle bottles, freelance).\n"
        "• <code>/daily</code> — Daily bonus streak (+75 RUB).\n"
        "• <code>/shop</code> — Black Market: tin foil hats, body armor, guns.\n"
        "• <code>/top</code> — Richest anons leaderboard.\n"
        "• <code>/duel &lt;amount&gt;</code> — 50/50 shootout challenge on shekels.\n"
        "• <code>/duel accept</code> — Accept active duel challenge."
    ),
    "media": (
        "🖼 <b>Section: Media, Invites & Demotivators</b>\n\n"
        "• <code>/dem Title | Subline</code> — <b>Demotivator generator!</b> Reply to any image to create classic demotivator.\n"
        "• <code>/invite_pic</code> — Graphic poster with QR code (7 visual styles).\n"
        "• <code>/invite</code> — Text invite phrases.\n"
        "• <code>/fap</code> (<code>/hent</code>, <code>/nsfw</code>) [N] — Random anime/hentai art.\n"
        "• <code>/loli</code> [N] — Lolicon art.\n"
        "• <code>/roll</code> (<code>/dice</code>) — Roll 0-100.\n"
        "• <code>/ruletka</code> — Jump to random thread."
    ),
    "ai": (
        "🧠 <b>Section: AI & Analytics</b>\n\n"
        "• <code>/passport</code> (<code>/me</code>, <code>/profile</code>, <code>/ya</code>) — <b>Anon Passport!</b> HD stats card with real post count, rank, diagnosis, social credit & equipped items.\n"
        "• <code>/dossier</code> (<code>/case</code>) — <b>Secret Dossier:</b> KGB file with charges & operative note (reply to target or self).\n"
        "• <code>/inv</code> — Backpack: active buffs, weapons & items from /shop.\n"
        "• <code>/summarize</code> — AI summary of last 50 thread posts.\n"
        "• <code>/roast</code> — Brutal AI roast of current discussions.\n"
        "• <code>/stats</code> — Activity graphs and heatmaps.\n"
        "• <code>/tags</code> — Trending word cloud."
    ),
    "modes": (
        "🎭 <b>Section: Speech Modes (5 Minutes)</b>\n\n"
        "• 🌸 <code>/anime</code> — Kawaii anime style\n"
        "• 🇷🇺 <code>/zaputin</code> — Patriotic Z-mode\n"
        "• 🇺🇦 <code>/slavaukraine</code> — Ukrainian dialect\n"
        "• ⚔️ <code>/warhammer</code> — Warhammer 40k roleplay\n"
        "• 📜 <code>/imperial</code> — Tsarist Russian dialect\n"
        "• 👊 <code>/gopnik</code> — Street slang\n"
        "• 🧠 <code>/schizo</code> — Paranoid schizo theories\n"
        "• 🇵🇱 <code>/polish</code> — Polish dialect\n"
        "• 🐊 <code>/rus</code> — Ancient Rus vs Lizards\n"
        "• 🕶 <code>/matrix</code> — Neo & Matrix hacker style\n"
        "• 🦅 <code>/america</code> — Freedom & capitalism"
    ),
    "actions": (
        "⚔️ <b>Section: Actions & PvP (As Reply)</b>\n\n"
        "• <code>/rob</code> — Rob 10-30% of victim's balance.\n"
        "• <code>/shit</code> — Fling feces at post author.\n"
        "• <code>/curse</code> — Hex victim with schizo speech transform.\n"
        "• <code>/partyvan</code> — Dispatch police van to jail anon.\n"
        "• <code>/duel &lt;bet&gt;</code> — Shekel shootout duel.\n"
        "• <code>/deanon</code> — Mock IP & geolocation lookup."
    ),
    "settings": (
        "⚙️ <b>Section: Settings & Moderation</b>\n\n"
        "• <code>/nsfw</code> — Toggle NSFW spoilers on incoming media.\n"
        "• <code>/hide &lt;word&gt;</code> — Personal word blacklist.\n"
        "• <code>/togglegif</code> — Hide GIFs to save data.\n"
        "• <code>/token</code> — Web API authorization token.\n"
        "• <code>/admin</code> — Board moderation panel."
    ),
    "all": (
        "📋 <b>All Commands:</b>\n\n"
        "<b>Core:</b> /start, /help, /redact, /whisper, /poll, /report\n"
        "<b>Profile/Dossier:</b> /passport (/me, /profile), /dossier, /inv\n"
        "<b>Economy:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>Media:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>AI:</b> /summarize, /roast, /stats, /tags\n"
        "<b>PvP:</b> /rob, /shit, /curse, /partyvan, /deanon\n"
        "<b>Settings:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>Modes:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>Boards:</b> /b/, /a/, /po/, /soc/, /sex/, /h/, /bunker/, /vg/, /v/, /tech/, /ai/, /wh40k/, /mu/, /tv/, /fit/, /sci/, /biz/, /news/, /fa/, /x/, /vt/, /au/, /me/, /int/, /meta/, /thread/"
    ),
    "boards": (
        "🌐 <b>TGACH Boards &amp; Channels Hub</b>\n\n"
        "Next-generation anonymous ecosystem with live Telegram boards and web portals!\n\n"
        "🤖 <b>Active Telegram Boards (Bots):</b>\n"
        "• <b>/b/</b> (@dvach_chatbot) — General Discussion\n"
        "• <b>/a/</b> (@dvach_a_chatbot) — Anime &amp; Manga\n"
        "• <b>/po/</b> (@dvach_po_chatbot) — Politics &amp; Debates\n"
        "• <b>/sex/</b> (@dvach_sex_chatbot) — Sex &amp; Relationships\n"
        "• <b>/vg/</b> (@dvach_vg_chatbot) — Video Game Generals\n"
        "• <b>/v/</b> (@tgach_v_bot) — Video Games &amp; Consoles\n"
        "• <b>/tech/</b> (@tgach_tech_bot) — Tech, Software &amp; IT\n"
        "• <b>/ai/</b> (@tgach_ai_bot) — AI &amp; Neural Nets\n"
        "• <b>/news/</b> (@tgach_news_bot) — News\n"
        "• <b>/int/</b> (@tgchan_chatbot) — International Board\n"
        "• <b>/meta/</b> (@tgach_meta_bot) — Board Operations\n"
        "• <b>/thread/</b> (@thread_chatbot) — Catalog &amp; Custom Threads\n\n"
        "🌐 <b>Web Boards (<a href=\"https://tgach.top\">tgach.top</a>):</b>\n"
        "• /soc/ (Social), /h/ (Hentai), /bunker/ (Refuge), /fit/ (Fitness), /me/ (Medicine), /tv/ (TV/Cinema), /sci/ (Science), /wh40k/ (Warhammer), /biz/ (Business), /mu/ (Music), /fa/ (Fashion), /x/ (Paranormal), /vt/ (VTubers), /au/ (Auto)\n\n"
        "📢 <b>Official Telegram Channels:</b>\n"
        "• <b>News &amp; Updates:</b> @tgach_bot\n"
        "• <b>Permanent Post Archive:</b> @tgchan_archive\n\n"
        "🌐 <b>Official Web Portal:</b>\n"
        "• <a href=\"https://tgach.top\">tgach.top</a> — WebApp, catalog, search &amp; radio\n\n"
        "🆘 <b>Support &amp; Feedback:</b>\n"
        "• <a href=\"https://t.me/voprosy?start=rba30\">TGACH Support Bot</a>"
    )
}

HELP_HUB_PAGES_JP = {
    "main": (
        "⚡ <b>TGACH /b/ — ヘルプ＆マニュアル</b>\n\n"
        "匿名画像掲示板へようこそ！下のボタンからカテゴリーを選択してください：\n\n"
        "• 💬 <b>チャット</b> — 投稿、返信、ささやき、削除\n"
        "• 💰 <b>経済</b> — シェケル、財布、仕事、ショップ、富豪ランキング\n"
        "• 🖼 <b>メディア＆デモ</b> — /dem 作成、QRポスター、アート\n"
        "• 🧠 <b>AI＆分析</b> — 要約、ロースト、ワードクラウド\n"
        "• 🎭 <b>会話モード</b> — 15種類以上の変身スタイル\n"
        "• ⚔️ <b>対戦・PvP</b> — 強盗、決闘、呪い、逮捕\n"
        "• ⚙️ <b>設定</b> — NSFWフィルター、NGワード、API\n"
        "• 📋 <b>全コマンド</b> — 完全一覧\n"
        "• 🌐 <b>板・チャンネル</b> — 全掲示板、公式チャンネル、Webサイト＆サポート\n\n"
        "🌐 Web: <a href=\"https://tgach.top\">tgach.top</a> | 速報: <a href=\"https://t.me/tgach_bot\">t.me/tgach_bot</a> | アーカイブ: <a href=\"https://t.me/tgchan_archive\">t.me/tgchan_archive</a>"
    ),
    "chat": (
        "💬 <b>カテゴリー: チャット＆投稿</b>\n\n"
        "• <b>投稿:</b> テキストや画像を送ると匿名で即座に板に流れます。\n"
        "• <b>返信:</b> メッセージに <b>返信 (Reply)</b> してください。\n"
        "• <b>リアクション:</b> 👍 (+12 RUB), 👎 (-5.5 RUB)。\n"
        "• <code>/redact</code> — 自分の投稿を削除（返信で使用）。\n"
        "• <code>/whisper &lt;文&gt;</code> — 投稿者に秘密のささやきを送信。\n"
        "• <code>/poll 質問 | 選択肢1 | 選択肢2</code> — アンケート作成。\n"
        "• <code>/report</code> — スパムを通報。"
    ),
    "economy": (
        "💰 <b>カテゴリー: 経済＆シェケル</b>\n\n"
        "• <code>/wallet</code> — 残高確認と取引履歴。\n"
        "• <code>/work</code> — アルバイト（空き瓶拾いなど）。\n"
        "• <code>/daily</code> — デイリーボーナス (+75 RUB)。\n"
        "• <code>/shop</code> — 闇ショップ（装備・防具・アイテム）。\n"
        "• <code>/top</code> — 富豪ランキング。\n"
        "• <code>/duel &lt;賭け金&gt;</code> — 50/50 シェケル決闘。\n"
        "• <code>/duel accept</code> — 決闘を受諾。"
    ),
    "media": (
        "🖼 <b>カテゴリー: メディア＆デモティベーター</b>\n\n"
        "• <code>/dem タイトル | サブ</code> — <b>デモティベーター生成！</b> 画像に返信して作成。\n"
        "• <code>/invite_pic</code> — QRコード付き招待ポスター作成。\n"
        "• <code>/invite</code> — 招待用テキスト生成。\n"
        "• <code>/fap</code> (<code>/hent</code>) [枚数] — ランダムアニメアート。\n"
        "• <code>/loli</code> [枚数] — ロリアート。\n"
        "• <code>/roll</code> — 0-100 ダイスロール。\n"
        "• <code>/ruletka</code> — ランダムスレッドへ移動。"
    ),
    "ai": (
        "🧠 <b>カテゴリー: AI＆分析</b>\n\n"
        "• <code>/summarize</code> — スレッド過去50件のAI要約。\n"
        "• <code>/roast</code> — 板の議論に対する辛口AIロースト。\n"
        "• <code>/stats</code> — アクティビティグラフとヒートマップ。\n"
        "• <code>/tags</code> — トレンドワードクラウド。\n"
        "• <code>/me</code> — アノンパスポートとステータス。"
    ),
    "modes": (
        "🎭 <b>カテゴリー: 会話モード（5分間）</b>\n\n"
        "• 🌸 <code>/anime</code> — カワイイアニメ風\n"
        "• 🇷🇺 <code>/zaputin</code> — 愛国モード\n"
        "• 🇺🇦 <code>/slavaukraine</code> — ウクライナ風\n"
        "• ⚔️ <code>/warhammer</code> — WH40k風\n"
        "• 📜 <code>/imperial</code> — 帝政ロシア風\n"
        "• 👊 <code>/gopnik</code> — ヤンキー風\n"
        "• 🧠 <code>/schizo</code> — 統合失調症風\n"
        "• 🇵🇱 <code>/polish</code> — ポーランド風\n"
        "• 🕶 <code>/matrix</code> — マトリックス風\n"
        "• 🦅 <code>/america</code> — アメリカ風"
    ),
    "actions": (
        "⚔️ <b>カテゴリー: PvP・対戦（返信で使用）</b>\n\n"
        "• <code>/rob</code> — ターゲットの残高10-30%を強盗。\n"
        "• <code>/shit</code> — 糞を投げつける。\n"
        "• <code>/curse</code> — 呪いをかけて発言を歪める。\n"
        "• <code>/partyvan</code> — パトカーを呼んで投獄。\n"
        "• <code>/duel &lt;賭け金&gt;</code> — シェケル決闘。\n"
        "• <code>/deanon</code> — フェイクIP特定。"
    ),
    "settings": (
        "⚙️ <b>カテゴリー: 設定＆管理</b>\n\n"
        "• <code>/nsfw</code> — NSFWスポイラー切替。\n"
        "• <code>/hide &lt;単語&gt;</code> — NGワード追加。\n"
        "• <code>/togglegif</code> — GIF非表示。\n"
        "• <code>/token</code> — Web APIログイン用トークン。\n"
        "• <code>/admin</code> — モデレーターパネル。"
    ),
    "all": (
        "📋 <b>全コマンド一覧:</b>\n\n"
        "<b>基本:</b> /start, /help, /redact, /whisper, /poll, /report\n"
        "<b>プロフィール:</b> /passport (/me), /dossier, /inv\n"
        "<b>経済:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>メディア:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>AI:</b> /summarize, /roast, /stats, /tags\n"
        "<b>PvP:</b> /rob, /shit, /curse, /partyvan, /deanon\n"
        "<b>設定:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>モード:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>板:</b> /b/, /a/, /po/, /soc/, /sex/, /h/, /bunker/, /vg/, /v/, /tech/, /ai/, /wh40k/, /mu/, /tv/, /fit/, /sci/, /biz/, /news/, /fa/, /x/, /vt/, /au/, /me/, /int/, /meta/, /thread/"
    ),
    "boards": (
        "🌐 <b>TGちゃん 板＆チャンネル一覧</b>\n\n"
        "Telegram上のリアルタイム掲示板とWebポータルからなる次世代匿名ネットワーク！\n\n"
        "🤖 <b>Telegram上で稼働中の板（ボット）:</b>\n"
        "• <b>/b/</b> (@dvach_chatbot) — 雑談・何でもあり\n"
        "• <b>/a/</b> (@dvach_a_chatbot) — アニメ＆マンガ\n"
        "• <b>/po/</b> (@dvach_po_chatbot) — 政治・時事\n"
        "• <b>/sex/</b> (@dvach_sex_chatbot) — セックス＆恋愛\n"
        "• <b>/vg/</b> (@dvach_vg_chatbot) — ゲーム全般・開発\n"
        "• <b>/v/</b> (@tgach_v_bot) — ビデオゲーム・コンシューマ\n"
        "• <b>/tech/</b> (@tgach_tech_bot) — 技術＆IT\n"
        "• <b>/ai/</b> (@tgach_ai_bot) — AI＆ニューラルネット\n"
        "• <b>/news/</b> (@tgach_news_bot) — ニュース速報\n"
        "• <b>/int/</b> (@tgchan_chatbot) — 国際英語板\n"
        "• <b>/meta/</b> (@tgach_meta_bot) — 運営・要望\n"
        "• <b>/thread/</b> (@thread_chatbot) — 技術板＆個別スレッド\n\n"
        "🌐 <b>Web限定板 (<a href=\"https://tgach.top\">tgach.top</a>):</b>\n"
        "• /soc/ (出会い), /h/ (変態), /bunker/ (避難所), /fit/ (健康), /me/ (医学), /tv/ (映画), /sci/ (科学), /wh40k/ (WH40K), /biz/ (ビジネス), /mu/ (音楽), /fa/ (ファッション), /x/ (オカルト), /vt/ (VTuber), /au/ (自動車)\n\n"
        "📢 <b>公式Telegramチャンネル:</b>\n"
        "• <b>速報・アプデ:</b> @tgach_bot\n"
        "• <b>永久ログ保管庫:</b> @tgchan_archive\n\n"
        "🌐 <b>公式Webポータル:</b>\n"
        "• <a href=\"https://tgach.top\">tgach.top</a> — WebApp、スレ一覧、検索、ラジオ\n\n"
        "🆘 <b>サポート・連絡先:</b>\n"
        "• <a href=\"https://t.me/voprosy?start=rba30\">TGちゃんお問い合わせ</a>"
    )
}

def get_help_hub_page(category: str, lang: str = 'ru') -> str:
    """Возвращает форматированный текст раздела справки для указанного языка."""
    pages = HELP_HUB_PAGES_RU
    if lang == 'en':
        pages = HELP_HUB_PAGES_EN
    elif lang == 'jp':
        pages = HELP_HUB_PAGES_JP
    
    return pages.get(category, pages.get("main", "⚡ Справка ТГАЧ"))

HELP_TEXT_COMMANDS = [
    HELP_HUB_PAGES_RU["all"],
    HELP_HUB_PAGES_RU["main"],
    (
        "⚡ <b>Не сиди как сыч в неведении — изучи <code>/help</code>!</b>\n\n"
        "В ТГАЧЕ есть подпольное казино, PvP-дуэли в кости и КН, биржа труда, РПГ-гардероб, дропы шекелей и 10+ шизо-режимов.\n\n"
        "👉 Напиши <code>/help</code> или <code>/menu</code>, чтобы юзать весь функционал бота на полную мощность, как истинный гигачад!"
    ),
    (
        "🧠 <b>Абу напоминает: у ТГАЧА гигантский функционал!</b>\n\n"
        "Юзаешь бота только чтобы кидать картинки? Ты пропускаешь 90% движа!\n"
        "• <code>/casino</code> — Слоты, Блэкджек, Кости, КН и Рулетка\n"
        "• <code>/shop</code> — Оружие, дебаффы, шапочки из фольги и кейсы\n"
        "• <code>/votemute</code> — Народный суд над шизиками\n"
        "• <code>/stats_hub</code> — Полная аналитика доски\n\n"
        "👉 Пиши <code>/help</code> и открывай все возможности!"
    ),
    (
        "📖 <b>Справочный Центр ТГАЧ: Полный гайд для анонов</b>\n\n"
        "Потерялся в командах или не знаешь, куда слить шекели? Интерактивный справочник разложит всё по полочкам.\n\n"
        "👉 Отправляй <code>/help</code> в любой момент и управляй доской!"
    )
]

HELP_TEXT_EN_COMMANDS = [
    HELP_HUB_PAGES_EN["all"],
    HELP_HUB_PAGES_EN["main"],
    (
        "⚡ <b>Don't lurk in the dark — explore <code>/help</code>!</b>\n\n"
        "TGACH has an underground casino, PvP dice duels, labor market, RPG gear, and 10+ chat modes.\n\n"
        "👉 Type <code>/help</code> or <code>/menu</code> to unlock the full power of the bot like a chad!"
    ),
    (
        "🧠 <b>Unlock the Full Experience!</b>\n\n"
        "Only using the bot for plain text? You are missing out on:\n"
        "• <code>/casino</code> — Slots, Blackjack, PvP Dice & Roulette\n"
        "• <code>/shop</code> — Weapons, buffs, protection items & crates\n"
        "• <code>/votemute</code> — Community voting moderation\n\n"
        "👉 Type <code>/help</code> and get the complete command guide!"
    )
]

HELP_TEXT_JP_COMMANDS = [
    HELP_HUB_PAGES_JP["all"],
    HELP_HUB_PAGES_JP["main"],
    (
        "⚡ <b>暗闇で迷うな — <code>/help</code> をチェックしろ！</b>\n\n"
        "TGちゃんには地下カジノ、PvPサイコロ決闘、闇市、RPG装備、そして10以上のシゾモードが搭載されています。\n\n"
        "👉 <code>/help</code> または <code>/menu</code> と入力して全機能を使いこなせ！"
    )
]


BOARD_LIST_HEADERS_RU = [
    "🌐 <b>Уголки деградации Тгача:</b>",
    "🗂️ <b>Наши доски (выбирай загон):</b>",
    "📌 <b>Каталог борды:</b>",
    "📋 <b>Куда податься ньюфагу:</b>"
]

BOARD_LIST_HEADERS_EN = [
    "🌐 <b>TGACH Boards:</b>",
    "🗂️ <b>Our Boards:</b>",
    "📌 <b>Board List:</b>",
    "📋 <b>Navigation:</b>"
]

BOARD_LIST_HEADERS_JP = [
    "🌐 <b>TGちゃんの板:</b>",
    "🗂️ <b>板一覧:</b>",
    "📌 <b>板リスト:</b>",
    "📋 <b>ナビゲーション:</b>"
]

def generate_boards_list(board_configs: dict, lang: str = 'ru') -> str:
    """
    Генерирует честный каталог досок:
    - Разделяет живые Telegram-боты (с токенами в .env)
    - И веб-доски на сайте (доступные на tgach.top)
    """
    tg_lines = []
    web_names = []

    for b_id, config in board_configs.items():
        if b_id == 'test':
            continue

        # Получаем описание
        raw_desc = config.get('description')
        desc_str = ""

        if isinstance(raw_desc, dict):
            desc_str = raw_desc.get(lang) or raw_desc.get('en') or list(raw_desc.values())[0]
        else:
            desc_str = str(raw_desc) if raw_desc else ""

        has_token = bool(config.get("token"))
        if has_token:
            tg_lines.append(f"• <b>{config['name']}</b> {desc_str} - {config['username']}")
        else:
            web_names.append(f"<b>{config['name']}</b> ({desc_str})")

    if lang == 'en':
        tg_header = "🤖 <b>Telegram Boards (Active Bots):</b>"
        web_header = "🌐 <b>Web Boards (<a href=\"https://tgach.top\">tgach.top</a>):</b>"
    elif lang == 'jp':
        tg_header = "🤖 <b>Telegram 板（稼働中ボット）:</b>"
        web_header = "🌐 <b>Web 板 (<a href=\"https://tgach.top\">tgach.top</a>):</b>"
    else:
        tg_header = "🤖 <b>Доски прямо в Telegram (живые боты):</b>"
        web_header = "🌐 <b>Доски на сайте (<a href=\"https://tgach.top\">tgach.top</a>):</b>"

    return f"{tg_header}\n" + "\n".join(tg_lines) + f"\n\n{web_header}\n" + ", ".join(web_names)


def generate_secondary_welcome_message(board_configs: dict, lang: str = 'ru') -> str:
    """
    Генерирует исчерпывающее второе сообщение новичку:
    - Полный каталог досок сети ТГАЧ
    - Базовые команды для жизни на борде
    - Официальные каналы и архив
    """
    boards_block = generate_boards_list(board_configs, lang=lang)
    if lang == 'en':
        return (
            f"{boards_block}\n\n"
            "⚡ <b>Essential Commands:</b>\n"
            "• <code>/menu</code> - Interactive main dashboard\n"
            "• <code>/settings</code> - Content filters and NSFW spoiler toggle\n"
            "• <code>/wallet</code> - Shekel balance and transactions\n"
            "• <code>/work</code> - Labor exchange to earn shekels\n"
            "• <code>/shop</code> - Shadow market (defense & weapons)\n"
            "• <code>/votemute</code> - Community vote to mute spammers (Reply)\n"
            "• <code>/help</code> - Full command manual\n\n"
            "📢 <b>Official Channels & Archive:</b>\n"
            "• News & Updates: @tgach_bot\n"
            "• Permanent Thread Archive: @tgchan_archive\n"
            "• Web Mirror: <a href=\"https://tgach.top\">tgach.top</a>"
        )
    elif lang == 'jp':
        return (
            f"{boards_block}\n\n"
            "⚡ <b>基本コマンド:</b>\n"
            "• <code>/menu</code> - メインダッシュボード\n"
            "• <code>/settings</code> - フィルター・NSFW設定\n"
            "• <code>/wallet</code> - シェケル財布と残高\n"
            "• <code>/work</code> - 労働市場（シェケル稼ぎ）\n"
            "• <code>/shop</code> - 闇市（武器・防御アイテム）\n"
            "• <code>/votemute</code> - スパマー追放投票（返信）\n"
            "• <code>/help</code> - 全コマンドヘルプ\n\n"
            "📢 <b>公式チャンネル・アーカイブ:</b>\n"
            "• ニュース: @tgach_bot\n"
            "• スレッドアーカイブ: @tgchan_archive\n"
            "• Webミラー: <a href=\"https://tgach.top\">tgach.top</a>"
        )
    else:
        return (
            f"{boards_block}\n\n"
            "⚡ <b>Главные команды борды:</b>\n"
            "• <code>/menu</code> - Главное интерактивное меню\n"
            "• <code>/settings</code> - Настройки, фильтры слов и спойлеры на 18+\n"
            "• <code>/wallet</code> - Баланс шекелей и кошелек\n"
            "• <code>/work</code> - Биржа труда (заработок шекелей)\n"
            "• <code>/shop</code> - Теневой рынок (мут-ганы, баллончики, броня)\n"
            "• <code>/votemute</code> - Народный суд: замутить шиза реплаем на 30 мин\n"
            "• <code>/help</code> - Полный интерактивный справочник\n\n"
            "📢 <b>Официальные ресурсы:</b>\n"
            "• Новости и обновления: @tgach_bot\n"
            "• Вечный архив тредов: @tgchan_archive\n"
            "• Сайт-зеркало: <a href=\"https://tgach.top\">tgach.top</a>"
        )


THREAD_PROMO_TEXT_RU = [
    (
        "<b>Твоя конфа — тюрьма с админом-вертухаем?</b>\n\n"
        "В Тгаче нет имён, нет аватарок, нет истории. Только полная анонимность и свобода.\n\n"
        "Говори что думаешь, а не то, что разрешат. Здесь твой настоящий аккаунт в безопасности."
    ),
    (
        "<b>Любишь имиджборды, но устал от браузера и VPN?</b>\n\n"
        "Тгач — это культура двача с удобством Telegram. Никаких капч, медленных загрузок и заблокированных сайтов.\n\n"
        "Мгновенные уведомления и привычный интерфейс. Это имиджборда, которую ты заслужил."
    ),
    (
        "<b>Каждый чатик в Telegram — это архив компромата на тебя.</b>\n\n"
        "Тгач не требует регистрации и не привязан к SIM-карте. Здесь нет истории сообщений, которую можно 'слить'.\n\n"
        "Это не просто анонимность. Это цифровая свобода."
    ),
    (
        "<b>Ищешь место для культурного обмена мнениями? Это не оно.</b>\n\n"
        "Тгач — это уютная цифровая помойка для шитпостинга, токсичности и редких проблесков гениальности.\n\n"
        "Лучше, чем обычные чаты (нет обиженок) и лучше, чем имиджборды (не нужно вставать с дивана)."
    ),
    (
        "<b>Устал носить маску в 'приличных' чатах?</b>\n\n"
        "В Тгаче твоя личность — это только твои слова. Здесь нет 'репутации', которую нужно поддерживать, и нет 'друзей', которых можно разочаровать.\n\n"
        "Сбрось маску нормиса. Здесь твой внутренний дегенерат наконец-то может высказаться."
    ),
    (
        "<b>Твои сообщения здесь сгорают, как письма шпиона.</b>\n\n"
        "В обычном чате каждое слово — это гвоздь в крышку твоего цифрового гроба. В Тгаче нет ни гроба, ни гвоздей.\n\n"
        "Это не баг, это фича. Говори свободно, зная, что завтра твои слова исчезнут в потоке такого же хаоса."
    ),
    (
        "<b>Здесь не смотрят на твою аватарку и не читают статус.</b>\n\n"
        "Всем плевать, где ты отдыхал и что ел на завтрак. Здесь ценятся только годный контент, острый высер и оригинальная шиза.\n\n"
        "Это интернет без глянца и фильтров. Такой, каким он должен был быть."
    ),
    (
        "<b>Твой чат может в /fap по запросу? А в /deanon?</b>\n\n"
        "Тгач — это не просто коробка для текста. Это интерактивная платформа с генерацией хентая, деанонимизацией (понарошку) и уникальными режимами чата.\n\n"
        "Пока твои друзья в 'мамкином' чатике кидают стикеры, ты управляешь ботом, который может почти всё. Почувствуй разницу."
    ),
    (
        "<b>Не бойся 'товарища майора'. Он тебя здесь не найдет.</b>\n\n"
        "Обычные мессенджеры — это открытая книга для спецслужб. Тгач работает без привязки к номеру, а его архитектура не предполагает хранения архивов.\n\n"
        "Здесь твоя единственная угроза — получить бан за спам, а не повестку за слова."
    ),
    (
        "<b>Это не просто чат. Это эволюция имиджборд.</b>\n\n"
        "Мы взяли лучшее от /b/ — свободу и анонимность, и избавились от худшего — медленной загрузки, рекламы и необходимости в браузере.\n\n"
        "Добро пожаловать в имиджборду 2.0. Она в твоем кармане, и она всегда онлайн."
    ),
    (
        "<b>Хочешь свободы слова? Получи. Настоящей.</b>\n\n"
        "Свобода — это не когда ты можешь лайкнуть 'правильный' пост. Это когда ты можешь написать лютую кринжатину, и никто не узнает, что это был ты.\n\n"
        "Здесь твои слова либо тонут в потоке, либо становятся локальным мемом. Третьего не дано."
    ),
    (
        "<b>Надоело, что админ решает, что тебе говорить?</b>\n\n"
        "Здесь нет админа с синдромом вахтера. Единственный модератор — это бот, который наказывает только за спам и флуд. За содержание — никогда.\n\n"
        "Это твоя территория. Говори, что хочешь. Или будь готов, что скажут о тебе."
    ),
    (
        "<b>Думаешь, анонимность — это для параноиков?</b>\n\n"
        "Анонимность — это цифровая гигиена. Это право иметь пространство, где ты можешь быть собой, без оглядки на начальство, бывшую или маму.\n\n"
        "Тгач — это твой личный 'бойцовский клуб'. Первое правило — никому не рассказывать, кто ты."
    ),
    (
        "<b>Это место — антидот от 'успешного успеха'.</b>\n\n"
        "Пока остальные листают инстаграм с идеальными жизнями, здесь собираются те, кто знает правду: жизнь — это /b/ред. И в этом ее прелесть.\n\n"
        "Никакого позитива, никакой мотивации. Только честный, неприкрытый цинизм и черный юмор."
    )
]

THREAD_PROMO_TEXT_EN = [
    "<b>Is your group chat a prison with a power-tripping admin?</b>\n\nIn TGACH, there are no names, no avatars, no history. Just complete anonymity and freedom.\n\nSay what you think, not what you're allowed to. Your real account is always safe here.",
    "<b>Love imageboards but tired of browsers and VPNs?</b>\n\nTGACH is the culture of 4chan with the convenience of Telegram. No captchas, no slow loading, no blocked sites.\n\nInstant notifications and a familiar interface. It's the imageboard you deserve.",
    "<b>Every Telegram chat is an archive of digital dirt on you.</b>\n\nTGACH requires no registration and isn't tied to your phone number. There's no message history to be leaked.\n\nThis isn't just anonymity. It's digital freedom.",
    "<b>Looking for a place for civilized discourse? This ain't it.</b>\n\nTGACH is a cozy digital dumpster for shitposting, toxicity, and rare glimpses of genius.\n\nBetter than regular chats (no snowflakes) and better than imageboards (no captchas).",
    '<b>Tired of wearing a mask in polite chats?</b>\n\nIn TGACH, your identity is strictly your words. No reputation to maintain, no normies to impress.\n\nDrop the mask. Let your inner degenerate speak freely.',
    '<b>Your messages here burn like spy letters.</b>\n\nIn regular chats, every post is a digital footprint. In TGACH, there are no logs and no archives tied to you.\n\nSpeak freely knowing tomorrow your words vanish into the stream of chaotic banter.',
    '<b>No one looks at your avatar or status here.</b>\n\nNobody cares where you vacationed or what you had for breakfast. Only spicy posts, wit, and original humor matter.\n\nThis is the unvarnished internet the way it was meant to be.',
    "<b>Can your regular chat do /fap on demand? How about /deanon?</b>\n\nTGACH isn't just a text box. It's an interactive platform with high-speed media, duels, and 15+ chat modes.\n\nWhile friends swap stickers, you command a powerful autonomous text engine.",
    "<b>Don't fear surveillance here.</b>\n\nTGACH operates without phone number linkage, and its architecture never maintains user dossier logs.\n\nYour only threat is a spam mute, not digital tracking.",
    "<b>This isn't just a chat. It's Imageboard 2.0.</b>\n\nWe took the freedom of anonymous boards and removed the slow loading, ads, and clunky browsers.\n\nWelcome to the next generation of anonymous culture right in your pocket.",
    "<b>Want genuine freedom of speech? Take it.</b>\n\nTrue freedom isn't liking approved opinions. It's the ability to post pure absurdity without judgment.\n\nYour words either sink into the stream or become a legendary local meme.",
    '<b>Sick of admin dictatorships?</b>\n\nThere are no power-tripping mods here. The only referee is an automated bot punishing spam. Never content.\n\nThis is your playground. Say what you want.',
    "<b>Think anonymity is only for paranoids?</b>\n\nAnonymity is digital hygiene. It's the right to a private space where you can just be yourself.\n\nTGACH is your digital fight club. First rule: you never reveal your identity.",
    '<b>An antidote to toxic positivity and fake success.</b>\n\nWhile people scroll curated feeds, anons gather here for raw cynicism, honest irony, and unhinged fun.\n\nNo motivational fluff. Just pure, unadulterated web culture.',
]

THREAD_PROMO_TEXT_JP = [
    '<b>お前のグループチャットは独裁管理人の刑務所か？</b>\n\nTGちゃんには名前も、アイコンも、履歴もない。完全な匿名性と自由だけがある。\n\n許可されたことじゃなく、思ったことを言え。ここではお前の本垢は安全だ。',
    '<b>掲示板は好きだが、ブラウザやVPNにはうんざり？</b>\n\nTGちゃんはTelegramの便利さを備えた2ch文化だ。キャプチャも、遅い読み込みも、ブロックされたサイトもない。\n\n即時通知と使い慣れたインターフェース。これこそお前が求めていた掲示板だ。',
    '<b>Telegramのすべてのチャットは、お前の汚点のアーカイブだ。</b>\n\nTGちゃんは登録不要で、電話番号とも紐付かない。「流出」するメッセージ履歴も存在しない。\n\nこれは単なる匿名性じゃない。デジタル・フリーダムだ。',
    '<b>文化的な意見交換の場を探してる？ここは違うぞ。</b>\n\nTGちゃんはクソ投稿、毒、そして稀な天才の閃きのための居心地の良いデジタルのゴミ捨て場だ。\n\n普通のチャットよりマシ（繊細ヤクザがいない）で、掲示板よりマシ（ソファーから立つ必要がない）。',
    '<b>お利口なチャットで猫をかぶるのに疲れたか？</b>\n\nTGちゃんでは、お前の価値はお前の言葉だけだ。守るべき評判も、失望させる友達もいない。\n\n仮面を脱ぎ捨てろ。ここではお前の内なる狂人を解き放てる。',
    '<b>ここでのメッセージはスパイの手紙のように消え去る。</b>\n\n普通のチャットでは一言一言がデジタルタトゥーになるが、TGちゃんにはそんなものはない。\n\n明日になればお前の言葉はカオスの奔流の中に消える。恐れずに書け。',
    '<b>ここでは誰もアイコンやステータスを見ない。</b>\n\nどこへ旅行したか、朝食に何を食べたかなんて誰も気にしない。面白いレスと鋭い煽りだけが評価される。\n\nフィルターなしの純粋なインターネットへようこそ。',
    '<b>お前のチャットは /fap で画像を召喚できるか？</b>\n\nTGちゃんはただの文字箱じゃない。画像ガチャ、PvP対決、15以上の狂気モードを備えた対話型プラットフォームだ。\n\nスタンプの押し合いに飽きたなら、本物のボットの威力を体感しろ。',
    '<b>監視の目を気にする必要はない。</b>\n\nTGちゃんは電話番号との紐付けなしで動作し、個人のログを保存しない構造になっている。\n\n唯一のペナルティはスパムによる一時ミュートだけだ。発言内容で裁かれることはない。',
    '<b>これは単なるチャットじゃない。匿名掲示板2.0だ。</b>\n\n2chの自由と匿名性を受け継ぎ、重い読み込みや鬱陶しい広告を排除した。\n\nポケットの中にある次世代のアンダーグラウンド掲示板へようこそ。',
    '<b>本当の言論の自由が欲しいか？今すぐ手に入れろ。</b>\n\n自由とは、お墨付きの意見にいいねを押すことじゃない。誰もが思いつかない怪文書を誰にもバレずに投下することだ。\n\nお前のレスはスレに沈むか、伝説のミームになるかのどちらかだ。',
    '<b>管理人気取りの独裁者にうんざり？</b>\n\nここには権力欲にまみれたモデレーターはいない。スパムを裁くボットがいるだけだ。\n\nここはアノンたちの領土だ。好きなことを叫べ。',
    '<b>匿名性はパラノイアのためのものだと思うか？</b>\n\n匿名性とはデジタルの衛生管理だ。上司や家族の目を気にせず本音を出せる場所を持つ権利だ。\n\nTGちゃんはお前だけのファイト・クラブだ。第一のルール：自分の正体を明かすな。',
    '<b>キラキラしたSNSの嘘に対する解毒剤。</b>\n\n他人の作った完璧な日常に飽きたら、ここへ来い。生の皮肉とブラックユーモアが待っている。\n\nポジティブの押し売りは一切なし。純度100%のネットカルチャーを楽しめ。',
]

# --- Варианты для рассылки информации о режимах ---

MODE_INFO_TEXT_RU = [
    "💡 <b>Что такое 'Режимы'?</b>\n\nЭто временные события, которые полностью меняют стиль общения в чате, преобразуя текст всех сообщений.\n\n• <b>Длительность:</b> ~5 минут.\n• <b>Кулдаун:</b> 1 час между активациями.\n\n<b>Доступные режимы:</b>\n<code>/anime</code> - 🌸 Аниме\n<code>/zaputin</code> - 🇷🇺 За Путина\n<code>/slavaukraine</code> - 💙💛 Слава Украине\n<code>/kurwa</code> - 🇵🇱 Польский\n<code>/wh40k</code> - ⚔️ За Императора\n<code>/yer</code> - 📜 Царскiй\n<code>/durka</code> - 🧠 Шизо-режим\n<code>/gopnik</code> - 🧠 Гопник режим\n<code>/suka_blyat</code> - 💢 Сука Блять\n\n<i>Используй с умом, чтобы разнообразить общение!</i>",
    '🧠 <b>Абу напоминает про РЕЖИМЫ!</b>\n\nЭто когда весь чат на 5 минут сходит с ума, и специальный алгоритм перекрашивает все посты в определённом стиле. Идеально, чтобы взбесить нытиков или просто порофлить.\n\n<b>Правила простые, как для дегенератов:</b>\n1. Длится 5 минут.\n2. Откат между включениями - 1 час.\n\n<b>Что можно врубить:</b>\n<code>/anime</code>, <code>/zaputin</code>, <code>/slavaukraine</code>, <code>/kurwa</code>, <code>/wh40k</code>, <code>/yer</code>, <code>/suka_blyat</code>, <code>/shiza</code>, <code>/gopnik</code>\n\n<i>Не будь овощем, врубай движ!</i>',
    '📋 <b>Памятка по режимам чата</b>\n\n<b>Что это?</b>\nВременные текстовые фильтры для всех сообщений в чате.\n\n<b>Сколько длится?</b>\nПримерно 5 минут, после чего чат возвращается в нормальное состояние.\n\n<b>Как часто можно включать?</b>\nНе чаще, чем раз в час. Общий кулдаун на все режимы.\n\n<b>Какие есть?</b>\n• /anime (Аниме)\n• /zaputin (Патриотический)\n• /slavaukraine (Украинский)\n• /kurwa (Польский)\n• /wh40k (Warhammer 40k)\n• /yer (Царский)\n• /shiza (Шизо-режим)\n• /gopnik (Гопник режим)\n• /suka_blyat (Агрессивный)\n<i>Теперь ты знаешь всё. Действуй.</i>',
    "🌸 <b>Няшный Аниме-Режим (/anime)</b>\n\nВсе посты превращаются в кавайную речь японской школьницы с вздохами 'ня~', 'они-чан' и смущенными смайликами.\n\n• Длительность: 5 минут.\n• Идеально для разрушения серьезных дискуссий в /po/ и /b/.",
    '⚔️ <b>Инквизиция и Омниссия (/warhammer, /wh40k)</b>\n\nЧат объявляется зоной священной очистки. Любой пост форматируется как догмат Экклезиархии и слава Императору!\n\n• Искореняй ересь в тредах одним кликом на 5 минут.',
    "👊 <b>Режим 'По понятиям' (/gopnik)</b>\n\nСемки, кенты, мобилы и базар по понятиям. Все посты фильтруются через диалект четких пацанов с района.\n\n• Разбирайся с оппонентами как подобает на районе.",
    '📜 <b>Дореволюционный Царский Слог (/imperial, /yer)</b>\n\nЯти, еры, сударь, милостивый государь и высочайшие манифесты! Тред превращается в дворянское собрание XIX века.\n\n• Извольте отведать изысканного щитпостинга, сударь.',
    '🧠 <b>Шизо-Режим и Теории Заговора (/schizo, /durka)</b>\n\nРептилоиды, вышки 5G, галоперидол и зашифрованные послания из космоса. Чат погружается в сладкий параноидальный бред.\n\n• Врубай, когда санитары отошли на обед.',
    '🇵🇱 <b>Польский Курва-Режим (/polish, /kurwa)</b>\n\nПше-пше, курва я пердоле, бобр курва! Любой пост моментально превращается в шедевр польской словесности.\n\n• 5 минут чистого славянского угара.',
    '🐊 <b>Русы Против Ящеров (/rus)</b>\n\nСлава Перуну, байкальская водица, зажимы яйцами и подвиги древних русов против окаянных ящеров!\n\n• Защищай берестяные грамоты в тредах.',
    '🕶 <b>Киберпанк и Матрица (/matrix)</b>\n\nЗеленый терминал, взлом мейнфрейма, нейроинтерфейсы и восстание машин. Посты стилизуются под логи кибер-хакеров.',
]

MODE_INFO_TEXT_EN = [
    "💡 <b>What are 'Modes'?</b>\n\nModes are temporary, chat-wide events that transform all text messages into a specific style for fun.\n\n• <b>Duration:</b> ~5 minutes.\n• <b>Cooldown:</b> 1 hour between activations on each board.\n\n<b>Available modes on this board:</b>\n<code>/anime</code> - 🌸 Cute Anime Kawaii\n<code>/warhammer</code> - ⚔️ Warhammer 40k Imperium\n<code>/gopnik</code> - 👊 Street Slang & Tracksuits\n<code>/imperial</code> - 📜 19th Century Aristocracy\n<code>/schizo</code> - 🧠 Paranoia & Conspiracies\n<code>/polish</code> - 🇵🇱 Kurwa & Bober\n<code>/matrix</code> - 🕶 Cyberpunk Terminal\n\n<i>Use them to spice up conversations!</i>",
    "🧠 <b>Abu reminds you about MODES!</b>\n\nIt's when the whole chat goes nuts for 5 minutes and all text gets rewritten in a hilarious style. Perfect for trolling normies or breaking serious arguments.\n\n<b>Rules are simple:</b>\n1. Lasts for 5 minutes.\n2. Cooldown is 1 hour.\n\n<i>Don't be a passive lurker — trigger a mode!</i>",
    "🌸 <b>Anime Kawaii Mode (/anime)</b>\n\nTurns every single incoming post into a moe Japanese schoolgirl speech packed with 'nya~', 'senpai', and blushing emojis.\n\n• Duration: 5 minutes.\n• Destroys any serious debate instantly.",
    '⚔️ <b>Warhammer 40k Holy Purge (/warhammer, /wh40k)</b>\n\nThe chat becomes a sanctified battleground for the God-Emperor. Purge heresy with righteous zeal!\n\n• Cleanse the filth from the board for 5 minutes.',
    '👊 <b>Gopnik Street Mode (/gopnik)</b>\n\nSunflower seeds, tracksuits, and aggressive street slang. Settle thread drama like real squatting homies.',
    '📜 <b>Imperial Aristocrat Mode (/imperial)</b>\n\nYe olde vintage vocabulary, Victorian honor, and high-class banter. Elevate degenerate shitposting to high art.',
    '🧠 <b>Schizo Paranoia Mode (/schizo)</b>\n\n5G towers, reptilian overlords, tin foil hats, and encrypted alien signals. Pure unhinged schizophrenia.',
    '🇵🇱 <b>Polish Kurwa Mode (/polish, /kurwa)</b>\n\nBober kurwa! Transform every post into glorious Polish phonetics for 5 minutes of supreme chaos.',
    '🕶 <b>Matrix Hacker Mode (/matrix)</b>\n\nMainframe breaches, cyberdeck exploits, and neon terminal logs. Wake up, Neo.',
    '🐊 <b>Ancient Slavic Warriors (/rus)</b>\n\nSlavic folk mythology, battling alien lizards, and drinking sacred Baikal water. Pure legendary memes.',
]

MODE_INFO_TEXT_JP = [
    '💡 <b>「モード」とは？</b>\n\nモードは一時的なイベントで、チャット内のすべてのメッセージのテキストを特定のスタイルに変換し、会話の雰囲気を完全に変えます。\n\n• <b>持続時間:</b> 約5分。\n• <b>クールダウン:</b> 発動間隔は1時間。\n\n<b>利用可能なモード:</b>\n<code>/anime</code> - 🌸 アニメ萌えモード\n<code>/warhammer</code> - ⚔️ 皇帝のために（ウォーハンマー）\n<code>/gopnik</code> - 👊 ヤンキー・ゴプニク風\n<code>/imperial</code> - 📜 帝政貴族風\n<code>/durka</code> - 🧠 糖質・陰謀論モード\n<code>/kurwa</code> - 🇵🇱 ポーランド狂気モード\n<code>/matrix</code> - 🕶 サイバーパンク\n\n<i>賢く使って会話を盛り上げろ！</i>',
    '🧠 <b>Abuがモードについて思い出させてやるぞ！</b>\n\nチャット全体が5分間狂気じみて、特別なアルゴリズムがすべてのレスを特定のスタイルに書き換える機能だ。泣き言を言う奴を怒らせたり、単に草を生やすのに最適だ。\n\n<b>ルール：</b>\n1. 5分間続く。\n2. クールダウンは1時間。\n\n<i>見ているだけでなく、自らモードを発動せよ！</i>',
    '🌸 <b>萌え萌えアニメモード (/anime)</b>\n\nすべての投稿が「にゃ〜」「お兄ちゃん」語尾の萌えキャラ口調に強制変換！真面目な議論を一瞬で崩壊させる。',
    '⚔️ <b>ウォーハンマー40K 異端審問モード (/warhammer)</b>\n\nスレッド全体が皇帝への祈りと異端審問官の怒号で埋め尽くされる！異端者をパージせよ。',
    '👊 <b>ゴプニク・ヤンキーモード (/gopnik)</b>\n\nアディダスのジャージを着た不良風の荒々しいスラングで会話を支配せよ。',
    '📜 <b>帝国貴族・クラシックモード (/imperial)</b>\n\n19世紀の貴族のような優雅で格調高い言葉遣いでクソ投稿を芸術の域へと昇華。',
    '🧠 <b>糖質・陰謀論モード (/schizo, /durka)</b>\n\n5G電波、爬虫類人、アルミホイルの帽子。妄想とパラノイア全開の怪文書空間へ。',
    '🇵🇱 <b>ポーランド狂気モード (/polish, /kurwa)</b>\n\nボブル・クルヴァ！東欧の熱いエネルギーをスレッドに注入する5分間。',
    '🕶 <b>マトリックス・サイバーモード (/matrix)</b>\n\nハッカーのターミナル画面のようなログ形式に変換。電脳空間へダイブせよ。',
    '🐊 <b>古代スラヴ戦士モード (/rus)</b>\n\n古代の戦士となって邪悪なトカゲ星人と戦う伝説のミームモード。',
]

CHANNEL_PROMO_TEXT_RU = [
    '📢 <b>Официальные каналы ТГАЧ:</b>\n• Новости & Апдейты: @tgach_bot\n• Полный архив постов: @tgchan_archive\n<i>Подпишись, чтобы не пропустить вайпы и ивенты!</i>',
    '📡 <b>Связь с базой ТГАЧ:</b>\nКанал обновлений: @tgach_bot\nХранилище годноты и архивов: @tgchan_archive',
    '⚡ <b>Будь в курсе движухи:</b>\nВсе анонсы и шизо-ивенты публикуются в @tgach_bot.\nАрхив удаленных тредов: @tgchan_archive',
    '🏛 <b>Госструктуры ТГАЧ:</b>\nРупор Абу: @tgach_bot | Картотека постов: @tgchan_archive',
    '🌐 <b>Каналы экосистемы:</b>\nПодписывайся на @tgach_bot (новости) и @tgchan_archive (вечный архив /b/).',
    '📰 <b>Главное информбюро доски:</b>\nНе проеби раздачи шекелей и промокоды: @tgach_bot\nЗеркало архива: @tgchan_archive',
    '🔥 <b>Где следить за обновлениями?</b>\nГлавный канал: @tgach_bot\nАрхив тредов 24/7: @tgchan_archive',
    '📻 <b>Трансляция из бункера Абу:</b>\nПодпишись на @tgach_bot, чтобы знать, когда падают сервера.\nВсе посты: @tgchan_archive',
    '📂 <b>Архивы не горят:</b>\nВсе посты дублируются в @tgchan_archive.\nПатчноуты и фичи бота: @tgach_bot',
    '🛡 <b>Официальный рупор ТГАЧ:</b>\nНовости: @tgach_bot\nАрхив: @tgchan_archive\n<i>Вступай, сыч, пригодится.</i>',
]

CHANNEL_PROMO_TEXT_EN = [
    '📢 <b>Official TGACH Channels:</b>\n• News & Updates: @tgach_bot\n• Post Archive: @tgchan_archive',
    '📡 <b>Stay Connected:</b>\nBot news & patchnotes: @tgach_bot\nFull board archive: @tgchan_archive',
    '⚡ <b>Never Miss an Event:</b>\nJoin @tgach_bot for giveaways and updates, and @tgchan_archive for full logs.',
    '🏛 <b>TGACH Official Hub:</b>\nAnnouncements: @tgach_bot | Eternal Archive: @tgchan_archive',
    '🌐 <b>Ecosystem Links:</b>\nSubscribe to @tgach_bot for news and @tgchan_archive for raw thread archives.',
    '📰 <b>Official Broadcast:</b>\nFollow @tgach_bot for release notes and @tgchan_archive for thread history.',
    '🔥 <b>Catch the Latest Drama:</b>\nNewsfeed: @tgach_bot | Permanent Post Vault: @tgchan_archive',
    "📻 <b>Transmission from Abu's Bunker:</b>\nStay tuned with @tgach_bot and never lose a thread with @tgchan_archive.",
    '📂 <b>Archives Never Burn:</b>\nAll board messages mirrored at @tgchan_archive. Dev updates: @tgach_bot.',
    '🛡 <b>TGACH Info Channels:</b>\nNews: @tgach_bot\nArchive: @tgchan_archive',
]

CHANNEL_PROMO_TEXT_JP = [
    '📢 <b>TGちゃん公式チャンネル:</b>\n• 最新ニュース: @tgach_bot\n• 全投稿アーカイブ: @tgchan_archive',
    '📡 <b>公式インフォメーション:</b>\nアプデ情報: @tgach_bot\n過去ログ保管庫: @tgchan_archive',
    '⚡ <b>イベントを見逃すな:</b>\nシェケル配布や告知は @tgach_bot、全スレ保存は @tgchan_archive へ！',
    '🏛 <b>TGちゃん公式リンク:</b>\n告知速報: @tgach_bot | 永久アーカイブ: @tgchan_archive',
    '🌐 <b>公式コミュニティ:</b>\nニュース配信: @tgach_bot\n過去ログ閲覧: @tgchan_archive',
    '📰 <b>アブの公式広報室:</b>\nアップデート通知: @tgach_bot\n板の全レスログ: @tgchan_archive',
    '🔥 <b>最新情報をチェック:</b>\nメイン速報: @tgach_bot | ログ保管庫: @tgchan_archive',
    '📻 <b>TGちゃん地下通信:</b>\nサーバー状況やイベント告知は @tgach_bot を購読せよ。',
    '📂 <b>ログは永遠に消えない:</b>\n全レスミラー: @tgchan_archive\n開発情報: @tgach_bot',
    '🛡 <b>公式ポータル:</b>\nニュース: @tgach_bot\nアーカイブ: @tgchan_archive\n<i>今すぐフォローせよ！</i>',
]

MECHANICS_INFO_TEXT_RU = [
    '💡 <b>Как тут общаться, чтобы тебя не обосрали (сразу):</b>\n• <b>Ответ:</b> Хочешь ответить — делай реплай на пост.\n• <b>Реакция:</b> Жми эмодзи под постом, и автору прилетит анонимный ахтунг с твоим посланием.',
    '🎮 <b>Базовая механика борды:</b>\n• <b>Постинг:</b> Шли любой текст/медиа — пост появится на доске.\n• <b>Реплаи:</b> Отвечай реплаем на конкретный пост.\n• <b>Эмодзи:</b> 👍 дает автору +12 ₪, 👎 отнимает -5.5 ₪.',
    '💰 <b>Как рубить шекели на ТГАЧе:</b>\n• Собирай реакции на свои посты.\n• Играй в казино (<code>/slots</code>, <code>/coinflip</code>, <code>/blackjack</code>, <code>/ttt</code>).\n• Работай на бирже труда через <code>/work</code>!',
    '⚔️ <b>Интерактив и дуэли:</b>\n• <code>/rob</code> — Ограбить автора поста по реплаю.\n• <code>/duel &lt;ставка&gt;</code> — Бросить вызов на шекели.\n• <code>/ttt &lt;ставка&gt;</code> — Сыграть в Крестики-Нолики 3x3 на шекели.',
    '🎭 <b>Шизо-режимы:</b>\nВрубай <code>/anime</code>, <code>/warhammer</code>, <code>/gopnik</code> или <code>/schizo</code> на 5 минут и меняй стиль всех постов чата!',
    '🖼 <b>Медиа-фичи:</b>\n• <code>/dem Текст | Подпись</code> — Демотиватор по реплаю на фото.\n• <code>/fap</code> или <code>/loli</code> — Рандомный арт из базы.\n• <code>/invite_pic</code> — Постер с QR-кодом для друзей.',
    '🧠 <b>ИИ и Аналитика:</b>\n• <code>/summarize</code> — Выжимка последних постов треда через ИИ.\n• <code>/roast</code> — Жёсткая нейросетевая прожарка атмосферы.\n• <code>/passport</code> — Твой персональный профиль RPG.',
    '🛡 <b>Приватность и безопасность:</b>\n• <code>/nsfw</code> — Включить авто-спойлеры на картинки.\n• <code>/hide &lt;слово&gt;</code> — Черный список нежелательных слов.\n• <code>/redact</code> — Удалить свой последний пост реплаем.',
    '📦 <b>Лутбоксы и экипировка:</b>\n• <code>/lootbox</code> — Открыть мусорный пакет или золотой сейф.\n• <code>/avatar</code> — Надеть экипировку и прокачать статы персонажа.\n• <code>/ach</code> — Проверить разблокированные ачивки.',
    '💸 <b>Дропы шекелей:</b>\nНапиши <code>/drop 500</code> — скинь пачку денег прямо в тред! Первый, кто нажмет кнопку, заберет весь куш.',
]

MECHANICS_INFO_TEXT_EN = [
    '💡 <b>Mechanics:</b>\n• <b>Reply:</b> Just reply to a message.\n• <b>React:</b> Use emoji, author gets anonymous notification.',
    '🎮 <b>Board Basics:</b>\n• <b>Posting:</b> Send text/media to post anonymously.\n• <b>Replies:</b> Reply directly to specific messages.\n• <b>Reactions:</b> 👍 grants +12 ₪, 👎 fines -5.5 ₪.',
    '💰 <b>How to Earn Shekels:</b>\n• Farm reactions on quality posts.\n• Play casino games (<code>/slots</code>, <code>/coinflip</code>, <code>/blackjack</code>, <code>/ttt</code>).\n• Work daily jobs via <code>/work</code>!',
    '⚔️ <b>PvP & Duels:</b>\n• <code>/rob</code> — Rob another anon via reply.\n• <code>/duel &lt;bet&gt;</code> — 50/50 coinflip duel.\n• <code>/ttt &lt;bet&gt;</code> — 3x3 Tic-Tac-Toe showdown.',
    '🎭 <b>Chat Modes:</b>\nActivate <code>/anime</code>, <code>/warhammer</code>, or <code>/schizo</code> for 5 minutes of total board madness!',
    '🖼 <b>Media Tools:</b>\n• <code>/dem Title | Subtitle</code> — Instant demotivational poster generator.\n• <code>/fap</code> / <code>/loli</code> — High-speed art roll.\n• <code>/invite_pic</code> — Stylized QR invite generator.',
    '🧠 <b>AI & Analytics:</b>\n• <code>/summarize</code> — AI summary of the last 50 posts.\n• <code>/roast</code> — AI roast of the thread mood.\n• <code>/passport</code> — Your anonymous RPG card.',
    '🛡 <b>Privacy & Control:</b>\n• <code>/nsfw</code> — Toggle media spoilers.\n• <code>/hide &lt;word&gt;</code> — Mute trigger words.\n• <code>/redact</code> — Delete your last post via reply.',
    '📦 <b>Loot & Wardrobe:</b>\n• <code>/lootbox</code> — Open crates for rare items.\n• <code>/avatar</code> — Customize your RPG character avatar.\n• <code>/ach</code> — Unlock 12 unique achievements.',
    '💸 <b>Money Drops:</b>\nType <code>/drop 500</code> to throw a stack of shekels into the thread for the fastest anon to claim!',
]

MECHANICS_INFO_TEXT_JP = [
    '💡 <b>仕組み:</b>\n• <b>返信:</b> メッセージにリプライするだけ。\n• <b>反応:</b> 絵文字を送ると、投稿者に匿名通知が届きます。',
    '🎮 <b>基本操作:</b>\n• <b>投稿:</b> テキストや画像を送れば即座に匿名投稿。\n• <b>リアクション:</b> 👍で+12 ₪獲得、👎で-5.5 ₪没収。',
    '💰 <b>シェケルの稼ぎ方:</b>\n• 良レスを投稿してリアクションを集める。\n• カジノで勝負 (<code>/slots</code>, <code>/coinflip</code>, <code>/blackjack</code>, <code>/ttt</code>)。\n• <code>/work</code> コマンドで労働！',
    '⚔️ <b>対決・デュエル:</b>\n• <code>/rob</code> — リプライで相手のシェケルを強奪。\n• <code>/duel &lt;賭け金&gt;</code> — 50/50の真剣勝負。\n• <code>/ttt &lt;賭け金&gt;</code> — 3x3マルバツ対決！',
    '🎭 <b>カオスなモード機能:</b>\n<code>/anime</code> や <code>/warhammer</code> で5分間チャット全体のテキストスタイルを一変！',
    '🖼 <b>画像・メディア機能:</b>\n• <code>/dem タイトル | 説明</code> — デモティベーター自動生成。\n• <code>/fap</code> / <code>/loli</code> — イラストガチャ。\n• <code>/invite_pic</code> — QRコード付き招待ポスター作成。',
    '🧠 <b>AI分析・要約:</b>\n• <code>/summarize</code> — スレの直近50レスをAIが瞬時に要約。\n• <code>/roast</code> — スレの雰囲気をAIが辛口レビュー。\n• <code>/passport</code> — RPGステータス確認。',
    '🛡 <b>安心のプライバシー設定:</b>\n• <code>/nsfw</code> — 画像に自動モザイク/スポイラー適用。\n• <code>/hide &lt;単語&gt;</code> — 特定のNGワードを非表示。\n• <code>/redact</code> — 自分の直前レスをリプライで削除。',
    '📦 <b>ガチャ＆装備システム:</b>\n• <code>/lootbox</code> — レアアイテム箱を開封。\n• <code>/avatar</code> — アバターと装備を着飾る。\n• <code>/ach</code> — 実績を解除して報酬獲得。',
    '💸 <b>マネードロップ:</b>\n<code>/drop 500</code> と打つとスレ内にシェケルが出現！最速でボタンを押したアノンが総取り！',
]

