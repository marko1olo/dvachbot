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
        "• <code>/summarize</code> (<code>/саммари</code>) — ИИ анализирует последние 50 постов треда и выдает краткую суть всех срачей и обсуждений.\n"
        "• <code>/roast</code> (<code>/прожарка</code>, <code>/база</code>) — Жесткая нейросетевая прожарка текущей атмосферы и участников борды.\n"
        "• <code>/stats</code> (<code>/activity</code>, <code>/стата</code>) — Полноценные графики активности, тепловые карты и динамика постов.\n"
        "• <code>/tags</code> (<code>/wordcloud</code>, <code>/теги</code>) — Облако ключевых тем и популярных слов за сутки.\n"
        "• <code>/me</code> (<code>/profile</code>, <code>/паспорт</code>) — Личная карточка анона: карма, стаж, количество постов и достижения."
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
        "<b>Общение:</b> /start, /help, /redact, /whisper, /poll, /report\n"
        "<b>Экономика:</b> /wallet, /work, /daily, /shop, /top, /duel\n"
        "<b>Медиа:</b> /dem, /invite_pic, /invite, /fap, /loli, /roll, /ruletka\n"
        "<b>ИИ/Инфо:</b> /summarize, /roast, /stats, /tags, /me\n"
        "<b>Интерактив:</b> /rob, /shit, /curse, /partyvan, /deanon\n"
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

# Сохраняем совместимость для старых вызовов и рассылок
HELP_TEXT_COMMANDS = [HELP_HUB_PAGES_RU["all"], HELP_HUB_PAGES_RU["main"]]
HELP_TEXT_EN_COMMANDS = [HELP_HUB_PAGES_EN["all"], HELP_HUB_PAGES_EN["main"]]
HELP_TEXT_JP_COMMANDS = [HELP_HUB_PAGES_JP["all"], HELP_HUB_PAGES_JP["main"]]
