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
        "• 📋 <b>Все команды</b> — Полный алфавитный справочник\n\n"
        "🌐 Канал архива: <a href=\"https://t.me/tgach_archive\">t.me/tgach_archive</a>"
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
        "💰 <b>Раздел: Экономика и Шекели</b>\n\n"
        "Шекели (₽) — внутрибордовая валюта для покупки артефактов, ставок в дуэлях и доминирования в топе.\n\n"
        "• <code>/wallet</code> (<code>/кошелек</code>, <code>/баланс</code>) — Баланс, история операций и вывод.\n"
        "• <code>/work</code> (<code>/earn</code>, <code>/bomj</code>, <code>/работа</code>) — Пойти на заработки (сдать бутылки, взломать пентагон, продать почку).\n"
        "• <code>/daily</code> (<code>/bonus</code>, <code>/ежедневно</code>) — Ежедневный бонус (+75 ₽ + множитель за непрерывную серию дней).\n"
        "• <code>/shop</code> (<code>/market</code>, <code>/магазин</code>) — Теневой Черный Рынок: шапочки из фольги, бронежилеты, пушки, сыворотка правды.\n"
        "• <code>/top</code> (<code>/leaders</code>, <code>/богачи</code>) — Рейтинг богатейших олигархов борды.\n"
        "• <code>/duel &lt;ставка&gt;</code> — Вызвать анона на дуэль на шекели (50/50 случайная перестрелка по реплаю).\n"
        "• <code>/duel accept</code> — Принять активный вызов на дуэль."
    ),
    "media": (
        "🖼 <b>Раздел: Медиа, Инвайты и Демотиваторы</b>\n\n"
        "• <code>/dem Заголовок | Подпись</code> — <b>Генератор демотиваторов!</b> Ответь реплаем на любое фото/картинку, и бот соберет каноничный постер с черной рамкой и шрифтом Impact.\n"
        "• <code>/invite_pic</code> — Сгенерировать стильный постер с QR-кодом для вербовки друзей (7 визуальных стилей: Киберпанк, Демотиватор, Матрица, Аниме, Вейпорвейв и др.).\n"
        "• <code>/invite</code> — Получить порцию отборных текстовых фраз для зазыва анонов.\n"
        "• <code>/fap</code> (<code>/hent</code>, <code>/nsfw</code>) [число] — Случайный аниме/хентай арт (можно писать <code>/fap 5</code> для пака из 5 штук).\n"
        "• <code>/loli</code> [число] — Лоликон-арт (безопасный/этти).\n"
        "• <code>/roll</code> (<code>/dice</code>, <code>/рулетка</code>) — Бросить кубик удачи от 0 до 100.\n"
        "• <code>/ruletka</code> — Перейти в случайный тред борды."
    ),
    "ai": (
        "🧠 <b>Раздел: Нейросети и Аналитика</b>\n\n"
        "• <code>/mystats</code> (<code>/профиль</code>) — <b>Личная карта деградации!</b> Генерирует стильную HD-карточку с реальным количеством постов, реакций, кринж-индексом и рангом.\n"
        "• <code>/passport</code> (<code>/me</code>, <code>/паспорт</code>) — <b>Паспорт Тгачера:</b> статус, экипировка из /shop, титул, диагноз и соц. рейтинг.\n"
        "• <code>/dossier</code> (<code>/дело</code>, <code>/досье</code>) — <b>Личное дело анона:</b> выписка из картотеки КГБ, инкриминируемые статьи и оперативная заметка (по реплаю или на себя).\n"
        "• <code>/summarize</code> (<code>/саммари</code>) — ИИ анализирует последние 50 постов треда и выдает краткую суть всех срачей.\n"
        "• <code>/roast</code> (<code>/прожарка</code>) — Жесткая нейросетевая прожарка атмосферы и участников борды.\n"
        "• <code>/stats</code> (<code>/activity</code>) — Полноценные графики активности доски (ритмы, тепловые карты и календарь).\n"
        "• <code>/tags</code> (<code>/теги</code>) — Облако ключевых тем и популярных слов за сутки."
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
        "• <code>/deanon</code> — Шуточный спуфинг-деанон с генерацией фейкового IP и адреса."
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
        "<b>Профиль/Досье:</b> /mystats, /passport, /dossier, /me\n"
        "<b>Экономика:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>Медиа:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>ИИ/Аналитика:</b> /summarize, /roast, /stats, /tags\n"
        "<b>Интерактив (Reply):</b> /dossier, /rob, /shit, /curse, /partyvan, /deanon\n"
        "<b>Настройки:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>Режимы:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>Доски:</b> /b, /po, /a, /vg, /sex, /int, /trash"
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
        "• 📋 <b>All Commands</b> — Complete alphabetized index\n\n"
        "🌐 Archive: <a href=\"https://t.me/tgach_archive\">t.me/tgach_archive</a>"
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
        "• <code>/summarize</code> — AI summary of last 50 thread posts.\n"
        "• <code>/roast</code> — Brutal AI roast of current discussions.\n"
        "• <code>/stats</code> — Activity graphs and heatmaps.\n"
        "• <code>/tags</code> — Trending word cloud.\n"
        "• <code>/me</code> (<code>/profile</code>) — Anon passport and stats."
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
        "<b>Economy:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>Media:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>AI:</b> /summarize, /roast, /stats, /tags, /me\n"
        "<b>PvP:</b> /rob, /shit, /curse, /partyvan, /deanon\n"
        "<b>Settings:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>Modes:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>Boards:</b> /b, /po, /a, /vg, /sex, /int, /trash"
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
        "• 📋 <b>全コマンド</b> — 完全一覧\n\n"
        "🌐 アーカイブ: <a href=\"https://t.me/tgach_archive\">t.me/tgach_archive</a>"
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
        "<b>経済:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>メディア:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>AI:</b> /summarize, /roast, /stats, /tags, /me\n"
        "<b>PvP:</b> /rob, /shit, /curse, /partyvan, /deanon\n"
        "<b>設定:</b> /nsfw, /hide, /togglegif, /token\n"
        "<b>モード:</b> /anime, /zaputin, /slavaukraine, /warhammer, /imperial, /gopnik, /schizo, /polish, /rus, /abu, /matrix, /oldweb, /jewish, /america\n"
        "<b>板:</b> /b, /po, /a, /vg, /sex, /int, /trash"
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

HELP_TEXT_COMMANDS = [HELP_HUB_PAGES_RU["all"], HELP_HUB_PAGES_RU["main"]]
HELP_TEXT_EN_COMMANDS = [HELP_HUB_PAGES_EN["all"], HELP_HUB_PAGES_EN["main"]]
HELP_TEXT_JP_COMMANDS = [HELP_HUB_PAGES_JP["all"], HELP_HUB_PAGES_JP["main"]]


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
    Генерирует список досок, выбирая описание на нужном языке.
    Убирает мусор вида {'ru': '...'} из вывода.
    """
    if lang == 'en':
        header = random.choice(BOARD_LIST_HEADERS_EN)
    elif lang == 'jp':
        header = random.choice(BOARD_LIST_HEADERS_JP)
    else:
        header = random.choice(BOARD_LIST_HEADERS_RU)

    board_lines = []

    for b_id, config in board_configs.items():
        if b_id == 'test':
            continue

        # Получаем описание
        raw_desc = config.get('description')
        desc_str = ""

        if isinstance(raw_desc, dict):
            # Пытаемся взять нужный язык, если нет — английский, если нет — первый попавшийся
            desc_str = raw_desc.get(lang) or raw_desc.get('en') or list(raw_desc.values())[0]
        else:
            desc_str = str(raw_desc) if raw_desc else ""

        # Формат: /b/ Описание - @link
        board_lines.append(
            f"<b>{config['name']}</b> {desc_str} - {config['username']}"
        )

    return f"{header}\n" + "\n".join(board_lines)

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
    (
        "<b>Is your group chat a prison with a power-tripping admin?</b>\n\n"
        "In TGACH, there are no names, no avatars, no history. Just complete anonymity and freedom.\n\n"
        "Say what you think, not what you're allowed to. Your real account is always safe here."
    ),
    (
        "<b>Love imageboards but tired of browsers and VPNs?</b>\n\n"
        "TGACH is the culture of 4chan with the convenience of Telegram. No captchas, no slow loading, no blocked sites.\n\n"
        "Instant notifications and a familiar interface. It's the imageboard you deserve."
    ),
    (
        "<b>Every Telegram chat is an archive of digital dirt on you.</b>\n\n"
        "TGACH requires no registration and isn't tied to your phone number. There's no message history to be leaked.\n\n"
        "This isn't just anonymity. It's digital freedom."
    ),
    (
        "<b>Looking for a place for civilized discourse? This ain't it.</b>\n\n"
        "TGACH is a cozy digital dumpster for shitposting, toxicity, and rare glimpses of genius.\n\n"
        "Better than regular chats (no snowflakes) and better than imageboards (no captchas)."
    )
]

THREAD_PROMO_TEXT_JP = [
    (
        "<b>お前のグループチャットは独裁管理人の刑務所か？</b>\n\n"
        "TGちゃんには名前も、アイコンも、履歴もない。完全な匿名性と自由だけがある。\n\n"
        "許可されたことじゃなく、思ったことを言え。ここではお前の本垢は安全だ。"
    ),
    (
        "<b>掲示板は好きだが、ブラウザやVPNにはうんざり？</b>\n\n"
        "TGちゃんはTelegramの便利さを備えた2ch文化だ。キャプチャも、遅い読み込みも、ブロックされたサイトもない。\n\n"
        "即時通知と使い慣れたインターフェース。これこそお前が求めていた掲示板だ。"
    ),
    (
        "<b>Telegramのすべてのチャットは、お前の汚点のアーカイブだ。</b>\n\n"
        "TGちゃんは登録不要で、電話番号とも紐付かない。「流出」するメッセージ履歴も存在しない。\n\n"
        "これは単なる匿名性じゃない。デジタル・フリーダムだ。"
    ),
    (
        "<b>文化的な意見交換の場を探してる？ここは違うぞ。</b>\n\n"
        "TGちゃんはクソ投稿、毒、そして稀な天才の閃きのための居心地の良いデジタルのゴミ捨て場だ。\n\n"
        "普通のチャットよりマシ（繊細ヤクザがいない）で、掲示板よりマシ（ソファーから立つ必要がない）。"
    )
]

# --- Варианты для рассылки информации о режимах ---

MODE_INFO_TEXT_RU = [
    (
        "💡 <b>Что такое 'Режимы'?</b>\n\n"
        "Это временные события, которые полностью меняют стиль общения в чате, преобразуя текст всех сообщений.\n\n"
        "• <b>Длительность:</b> ~5 минут.\n"
        "• <b>Кулдаун:</b> 1 час между активациями.\n\n"
        "<b>Доступные режимы:</b>\n"
        "<code>/anime</code> - 🌸 Аниме\n"
        "<code>/zaputin</code> - 🇷🇺 За Путина\n"
        "<code>/slavaukraine</code> - 💙💛 Слава Украине\n"
        "<code>/kurwa</code> - 🇵🇱 Польский\n"
        "<code>/wh40k</code> - ⚔️ За Императора\n"
        "<code>/yer</code> - 📜 Царскiй\n"
        "<code>/durka</code> - 🧠 Шизо-режим\n"
        "<code>/gopnik</code> - 🧠 Гопник режим\n"
        "<code>/suka_blyat</code> - 💢 Сука Блять\n"
        "\n"
        "<i>Используй с умом, чтобы разнообразить общение!</i>"
    ),
    (
        "🧠 <b>Абу напоминает про РЕЖИМЫ!</b>\n\n"
        "Это когда весь чат на 5 минут сходит с ума, и специальный алгоритм перекрашивает все посты в определённом стиле. Идеально, чтобы взбесить нытиков или просто порофлить.\n\n"
        "<b>Правила простые, как для дегенератов:</b>\n"
        "1. Длится 5 минут.\n"
        "2. Откат между включениями - 1 час.\n\n"
        "<b>Что можно врубить:</b>\n"
        "<code>/anime</code>, <code>/zaputin</code>, <code>/slavaukraine</code>, <code>/kurwa</code>, <code>/wh40k</code>, <code>/yer</code>, <code>/suka_blyat</code>, <code>/shiza</code>, <code>/gopnik</code>\n\n"
        "<i>Не будь овощем, врубай движ!</i>"
    ),
    (
        "📋 <b>Памятка по режимам чата</b>\n\n"
        "<b>Что это?</b>\n"
        "Временные текстовые фильтры для всех сообщений в чате.\n\n"
        "<b>Сколько длится?</b>\n"
        "Примерно 5 минут, после чего чат возвращается в нормальное состояние.\n\n"
        "<b>Как часто можно включать?</b>\n"
        "Не чаще, чем раз в час. Общий кулдаун на все режимы.\n\n"
        "<b>Какие есть?</b>\n"
        "• /anime (Аниме)\n"
        "• /zaputin (Патриотический)\n"
        "• /slavaukraine (Украинский)\n"
        "• /kurwa (Польский)\n"
        "• /wh40k (Warhammer 40k)\n"
        "• /yer (Царский)\n"
        "• /shiza (Шизо-режим)\n"
        "• /gopnik (Гопник режим)\n"
        "• /suka_blyat (Агрессивный)\n"
        "<i>Теперь ты знаешь всё. Действуй.</i>"
    )
]

MODE_INFO_TEXT_EN = [
    (
        "💡 <b>What are 'Modes'?</b>\n\n"
        "Modes are temporary, chat-wide events that transform all text messages into a specific style for fun.\n\n"
        "• <b>Duration:</b> ~5 minutes.\n"
        "• <b>Cooldown:</b> 1 hour between activations on each board.\n\n"
        "<b>Available modes on this board:</b>\n"
        "<code>/anime</code> - 🌸 Activate Anime mode\n\n"
        "<i>Use them to spice things up!</i>"
    ),
    (
        "🧠 <b>Abu reminds you about MODES!</b>\n\n"
        "It's when the whole chat goes nuts for 5 minutes and all text gets fucked up in a specific style. Perfect for pissing off normies or just for laughs.\n\n"
        "<b>Rules are simple, even for you degenerates:</b>\n"
        "1. Lasts for 5 minutes.\n"
        "2. Cooldown is 1 hour.\n\n"
        "<b>What you can turn on:</b>\n"
        "<code>/anime</code> - for weebs and faggots\n\n"
        "<i>Now you know. Don't be a lurker.</i>"
    )
]

MODE_INFO_TEXT_JP = [
    (
        "💡 <b>「モード」とは？</b>\n\n"
        "モードは一時的なイベントで、チャット内のすべてのメッセージのテキストを特定のスタイルに変換し、会話の雰囲気を完全に変えます。\n\n"
        "• <b>持続時間:</b> 約5分。\n"
        "• <b>クールダウン:</b> 発動間隔は1時間。\n\n"
        "<b>利用可能なモード:</b>\n"
        "<code>/anime</code> - 🌸 アニメ\n"
        "<code>/zaputin</code> - 🇷🇺 プーチン支持\n"
        "<code>/slavaukraine</code> - 💙💛 ウクライナ支持\n"
        "<code>/kurwa</code> - 🇵🇱 ポーランド\n"
        "<code>/wh40k</code> - ⚔️ 皇帝のために\n"
        "<code>/yer</code> - 📜 帝政\n"
        "<code>/durka</code> - 🧠 糖質モード\n"
        "<code>/gopnik</code> - 🧠 ヤンキーモード\n"
        "<code>/suka_blyat</code> - 💢 スーカ・ブリャリ\n"
        "<i>賢く使って会話を盛り上げろ！</i>"
    ),
    (
        "🧠 <b>Abuがモードについて思い出させてやるぞ！</b>\n\n"
        "チャット全体が5分間狂気じみて、特別なアルゴリズムがすべてのレスを特定のスタイルに書き換える機能だ。泣き言を言う奴を怒らせたり、単に草を生やすのに最適だ。\n\n"
        "<b>ルールは簡単だ、お前らバカでも分かる：</b>\n"
        "1. 5分間続く。\n"
        "2. 再発動までのクールダウンは1時間。\n\n"
        "<b>起動できるもの：</b>\n"
        "<code>/anime</code>, <code>/zaputin</code>, <code>/slavaukraine</code>, <code>/kurwa</code>, <code>/wh40k</code>, <code>/yer</code>, <code>/suka_blyat</code>, <code>/shiza</code>, <code>/gopnik</code>\n\n"
        "<i>野菜になってないで、アクションを起こせ！</i>"
    )
]

CHANNEL_PROMO_TEXT_RU = [
    "📢 <b>Подпишись:</b>\nНовости: @tgach_bot\nАрхив (все посты): @tgchan_archive"
]

CHANNEL_PROMO_TEXT_EN = [
    "📢 <b>Subscribe:</b>\nNews: @tgach_bot\nArchive (all posts): @tgchan_archive"
]

CHANNEL_PROMO_TEXT_JP = [
    "📢 <b>購読する:</b>\nニュース: @tgach_bot\nアーカイブ (全レス): @tgchan_archive"
]


MECHANICS_INFO_TEXT_RU = [
    "💡 <b>Как тут общаться, чтобы тебя не обосрали (сразу):</b>\n• <b>Ответ:</b> Хочешь ответить — делай реплай на пост.\n• <b>Реакция:</b> Жми эмодзи под постом, и автору прилетит анонимный ахтунг с твоим посланием."
]

MECHANICS_INFO_TEXT_EN = [
    "💡 <b>Mechanics:</b>\n• <b>Reply:</b> Just reply to a message.\n• <b>React:</b> Use emoji, author gets anonymous notification."
]

MECHANICS_INFO_TEXT_JP = [
    "💡 <b>仕組み:</b>\n• <b>返信:</b> メッセージにリプライするだけ。\n• <b>反応:</b> 絵文字を送ると、投稿者に匿名通知が届きます。"
]
