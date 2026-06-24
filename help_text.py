# help_text.py
import random
HELP_TEXT_COMMANDS = [
    (
        "Канал ТГАЧ АРХИВ (все посты) https://t.me/tgach_archive\n"
        "Переход по доскам: /b /po /a /vg /sex /int /trash\n\n"
        "<b>Команды бота:</b>\n\n"
        "/start — Перезапуск\n"
        "/help — Помощь\n"
        "/stats — Статистика\n"
        "/wallet — Твой кошелек\n"
        "/shop — Теневой Магазин\n"
        "/me — Твой профиль\n"
        "/roll — Ролл (0-100)\n"
        "/poll тема | вариант1 | вариант2 — Создать опрос\n"
        "/invite — Пригласить анонов\n"
        "/deanon — Деанон (шуточный)\n"
        "/active — Активность досок\n"
        "/token — Токен для апихи\n"
        "/ruletka — Телеграм-рулетка\n"
        "/whisper <текст> — Тайный шёпот (реплай)\n"
        "/redact — Удалить свой высер (реплай)\n\n"
        "<b>Контент и Медиа:</b>\n"
        "/hent /fap /nsfw — Аниме/Хентай\n"
        "/loli /lolicon — Лоли арт\n"
        "<i>(Можно писать /fap 5, чтобы получить сразу 5 картинок)</i>\n\n"
        "<b>Режимы (меняют стиль общения на 5 мин):</b>\n"
        "/anime — 🌸 Аниме режим\n"
        "/zaputin — 🇷🇺 Z-режим\n"
        "/slavaukraine — 🇺🇦 Украинский режим\n"
        "/polish — 🇵🇱 Польский режим\n"
        "/warhammer — ⚔️ За Императора!\n"
        "/imperial — 📜 Царский режим\n"
        "/gopnik — 👊 Пацанский режим\n"
        "/schizo — 🧠 Режим шизофреника\n"
        "/matrix — 🟩 Матрица\n"
        "/america — 🦅 Liberty-режим\n"
        "/holiday — 🎄 Праздничный режим\n"
        "/oldweb — 🖥️ Старый интернет\n"
        "/jewish — 📜 Талмудический диспут\n\n"
        "<b>Инструменты (Нейросети):</b>\n"
        "/summarize — Краткий пересказ чата нейросетью\n"
        "/roast — Жесткая шизо-прожарка борды\n"
        "/generate текст — Картинка с текстом для вайпа\n\n"
        "Канал новостей: @tgach_bot\n"
        "Связь с админом: t.me/voprosy?start=rba30\n\n"
        "<b>Как отвечать:</b> Просто ответь (Reply) на сообщение.\n"
        "<b>Реакции:</b> Ставь реакции на сообщения, автор получит анонимное уведомление."
    ),
    (
        "Канал ТГАЧ АРХИВ (все посты) https://t.me/tgach_archive\n\n"
        "<b>Абу напоминает список команд:</b>\n\n"
        "/start — Если заблудился\n"
        "/help — Если забыл команды\n"
        "/stats — Посмотреть статистику\n"
        "/roll — Испытать удачу\n"
        "/me — Инфо о себе\n"
        "/wallet — Твой кошелек\n"
        "/shop — Черный рынок\n"
        "/poll — Сделать голосование\n"
        "/invite — Текст для инвайта\n"
        "/deanon — Вычислить по IP\n"
        "/token — Вход на сайт\n\n"
        "<b>Развлечения:</b>\n"
        "/ruletka — Рандом тред\n"
        "/fap /hent — Хентай\n"
        "/loli — Лоли\n\n"
        "Можно писать /fap5 /loli3 — придет 8 картинок\n\n"
        "<b>Режимы общения:</b>\n"
        "🌸 /anime, 🇷🇺 /zaputin, 🇺🇦 /slavaukraine\n"
        "🇵🇱 /polish, ⚔️ /wh40k, 📜 /yer\n"
        "👊 /gopnik, 🧠 /shiza, 💢 /suka_blyat\n"
        "🟩 /matrix, 🦅 /america, 🎄 /holiday, 🖥️ /oldweb, 📜 /jewish\n\n"
        "<b>Полезное (Нейросети):</b>\n"
        "/summarize — Саммари чата\n"
        "/roast — Авто-прожарка срачей\n"
        "/active — Где сейчас актив?\n\n"
        "Новости: @tgach_bot\n"
        "Админ: t.me/voprosy?start=rba30"
        "Переход по доскам: /b /po /a /vg /sex /int /trash\n\n"
    )
]

HELP_TEXT_EN_COMMANDS = [
    (
        "TGACH ARCHIVE Channel: https://t.me/tgach_archive\n"
        "Boards: /b /po /a /vg /sex /int /trash\n\n"
        "<b>Bot Commands:</b>\n\n"
        "/start - Restart\n"
        "/help - Help\n"
        "/stats - Statistics\n"
        "/me - Your Profile\n"
        "/wallet - Your Wallet\n"
        "/shop - Black Market\n"
        "/roll - Roll (0-100)\n"
        "/poll topic | opt1 | opt2 - Create Poll\n"
        "/invite - Invite text\n"
        "/deanon - Fake Deanon\n"
        "/active - Board Activity\n"
        "/token - Website Token\n"
        "/ruletka - Roulette Thread\n\n"
        "<b>Media & Content:</b>\n"
        "/hent /fap /nsfw - Hentai\n"
        "/loli /lolicon - Loli Art\n"
        "<i>(Tip: use /fap 5 to get 5 images at once)</i>\n\n"
        "<b>Chat Modes (5 min style change):</b>\n"
        "/anime - 🌸 Anime Mode\n"
        "/zaputin - 🇷🇺 Z-Mode\n"
        "/slavaukraine - 🇺🇦 UA-Mode\n"
        "/polish - 🇵🇱 Polish Mode\n"
        "/warhammer - ⚔️ WH40k\n"
        "/imperial - 📜 Tsarist Mode\n"
        "/gopnik - 👊 Gopnik Mode\n"
        "/schizo - 🧠 Schizo Mode\n"
        "/matrix - 🟩 Matrix Mode\n"
        "/america - 🦅 Liberty Mode\n"
        "/holiday - 🎄 Holiday Mode\n"
        "/oldweb - 🖥️ Old Web Mode\n"
        "/jewish - 📜 Talmudic Debate Mode\n\n"
        "<b>Tools (AI):</b>\n"
        "/summarize - AI Chat Summary\n"
        "/roast - AI Schizo Roast of the board\n"
        "/generate text - Wipe Image\n\n"
        "News Channel: @tgach_bot\n"
        "Contact Admin: t.me/voprosy?start=rba30\n\n"
        "<b>Replies:</b> Simply reply to a message.\n"
        "<b>Reactions:</b> Use emoji reactions, author gets anonymous notification."
    ),
    (
        "TGACH ARCHIVE (all posts) https://t.me/tgach_archive\n\n"
        "<b>Abu reminds you of the commands:</b>\n\n"
        "/start - If you are lost\n"
        "/help - If you are stupid\n"
        "/stats - Chat statistics\n"
        "/roll - Try your luck\n"
        "/me - Who are you?\n"
        "/wallet - Your wallet\n"
        "/shop - Store (Black Market)\n"
        "/poll - Create a poll\n"
        "/invite - Invite friends\n"
        "/deanon - Cyberbully (joke)\n"
        "/token - Web login\n\n"
        "<b>Content:</b>\n"
        "/hent /fap - Jerk off\n"
        "/loli - Loli\n"
        "/ruletka - Roulette\n\n"
        "<b>Modes:</b>\n"
        "🌸 /anime, 🇷🇺 /zaputin, 🇺🇦 /slavaukraine\n"
        "🇵🇱 /polish, ⚔️ /wh40k, 📜 /yer\n"
        "👊 /gopnik, 🧠 /shiza, 💢 /suka_blyat\n"
        "🟩 /matrix, 🦅 /america, 🎄 /holiday, 🖥️ /oldweb, 📜 /jewish\n\n"
        "<b>Useful (AI):</b>\n"
        "/summarize - Chat summary\n"
        "/roast - Board Roast\n"
        "/active - Board activity\n\n"
        "News: @tgach_bot"
    )
]

HELP_TEXT_JP_COMMANDS = [
    (
        "TGACHアーカイブ (全レス) https://t.me/tgach_archive\n"
        "板移動: /b /po /a /vg /sex /int /trash\n\n"
        "<b>利用可能なコマンド:</b>\n\n"
        "/start - 開始\n"
        "/help - ヘルプ\n"
        "/stats - 統計\n"
        "/me - プロフィール\n"
        "/shop - ブラックマーケット\n"
        "/roll - サイコロ (0-100)\n"
        "/poll テーマ | 選択肢1 | 選択肢2 - 投票作成\n"
        "/invite - 招待テキスト\n"
        "/deanon - 特定ごっこ\n"
        "/active - 板の勢い\n"
        "/token - サイト用トークン\n"
        "/ruletka - ルーレットスレ\n\n"
        "<b>メディア:</b>\n"
        "/hent /fap /nsfw - エロ画像\n"
        "/loli /lolicon - ロリ画像\n"
        "<i>(例: /fap 5 で5枚送信)</i>\n\n"
        "<b>チャットモード (5分間):</b>\n"
        "/anime - 🌸 アニメモード\n"
        "/zaputin - 🇷🇺 Zモード\n"
        "/slavaukraine - 🇺🇦 ウクライナモード\n"
        "/polish - 🇵🇱 ポーランドモード\n"
        "/warhammer - ⚔️ WH40k\n"
        "/imperial - 📜 帝政モード\n"
        "/gopnik - 👊 ヤンキーモード\n"
        "/schizo - 🧠 糖質モード\n"
        "/matrix - 🟩 マトリックス\n"
        "/america - 🦅 リバティ\n"
        "/holiday - 🎄 ホリデー\n"
        "/oldweb - 🖥️ オールドウェブ\n"
        "/jewish - 📜 タルムード議論\n\n"
        "<b>ツール (AI):</b>\n"
        "/summarize - チャットのAI要約\n"
        "/roast - AIによる板の煽り\n"
        "/generate テキスト - ワイプ画像生成\n\n"
        "ニュース: @tgach_bot\n"
        "管理人: t.me/voprosy?start=rba30\n\n"
        "<b>返信:</b> メッセージにリプライしてください。\n"
        "<b>リアクション:</b> 絵文字を送ると、投稿者に匿名通知が届きます。"
    ),
    (
        "TGACHアーカイブ https://t.me/tgach_archive\n\n"
        "<b>コマンドリスト:</b>\n\n"
        "/start - 迷子ならこれ\n"
        "/help - バカならこれ\n"
        "/stats - クソ投稿の統計\n"
        "/roll - 運試し\n"
        "/me - お前\n"
        "/shop - お店\n"
        "/poll - 投票を作る\n"
        "/invite - 友達を呼ぶ\n"
        "/deanon - 特定する（嘘）\n"
        "/token - ウェブログイン\n\n"
        "<b>コンテンツ:</b>\n"
        "/hent /fap - シコる\n"
        "/loli - ロリ\n"
        "/ruletka - ルーレット\n\n"
        "<b>モード:</b>\n"
        "🌸 /anime, 🇷🇺 /zaputin, 🇺🇦 /slavaukraine\n"
        "🇵🇱 /polish, ⚔️ /wh40k, 📜 /yer\n"
        "👊 /gopnik, 🧠 /shiza, 💢 /suka_blyat\n"
        "🟩 /matrix, 🦅 /america, 🎄 /holiday, 🖥️ /oldweb, 📜 /jewish\n\n"
        "<b>便利機能 (AI):</b>\n"
        "/summarize - 要約\n"
        "/roast - 板の煽り\n"
        "/active - 勢い\n\n"
        "ニュース: @tgach_bot"
    )
]

# --- Варианты для рассылки списка досок ---

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
        "<code>/matrix</code> - 🟩 Матрица\n"
        "<code>/america</code> - 🦅 Американский режим\n"
        "<code>/holiday</code> - 🎄 Новый год/праздники\n"
        "<code>/oldweb</code> - 🖥️ Старый интернет\n"
        "<code>/jewish</code> - 📜 Талмудический диспут\n\n"
        "<i>Используй с умом, чтобы разнообразить общение!</i>"
    ),
    (
        "🧠 <b>Абу напоминает про РЕЖИМЫ!</b>\n\n"
        "Это когда весь чат на 5 минут сходит с ума, и специальный алгоритм перекрашивает все посты в определённом стиле. Идеально, чтобы взбесить нытиков или просто порофлить.\n\n"
        "<b>Правила простые, как для дегенератов:</b>\n"
        "1. Длится 5 минут.\n"
        "2. Откат между включениями - 1 час.\n\n"
        "<b>Что можно врубить:</b>\n"
        "<code>/anime</code>, <code>/zaputin</code>, <code>/slavaukraine</code>, <code>/kurwa</code>, <code>/wh40k</code>, <code>/yer</code>, <code>/suka_blyat</code>, <code>/shiza</code>, <code>/gopnik</code>, <code>/matrix</code>, <code>/america</code>, <code>/holiday</code>, <code>/oldweb</code>, <code>/jewish</code>\n\n"
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
        "• /matrix (Матрица)\n"
        "• /america (Американский)\n"
        "• /holiday (Праздничный)\n"
        "• /oldweb (Старый интернет)\n"
        "• /jewish (Талмудический диспут)\n\n"
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
        "<code>/matrix</code> - 🟩 マトリックス\n"
        "<code>/america</code> - 🦅 リバティ\n"
        "<code>/holiday</code> - 🎄 ホリデー\n"
        "<code>/oldweb</code> - 🖥️ オールドウェブ\n"
        "<code>/jewish</code> - 📜 タルムード議論\n\n"
        "<i>賢く使って会話を盛り上げろ！</i>"
    ),
    (
        "🧠 <b>Abuがモードについて思い出させてやるぞ！</b>\n\n"
        "チャット全体が5分間狂気じみて、特別なアルゴリズムがすべてのレスを特定のスタイルに書き換える機能だ。泣き言を言う奴を怒らせたり、単に草を生やすのに最適だ。\n\n"
        "<b>ルールは簡単だ、お前らバカでも分かる：</b>\n"
        "1. 5分間続く。\n"
        "2. 再発動までのクールダウンは1時間。\n\n"
        "<b>起動できるもの：</b>\n"
        "<code>/anime</code>, <code>/zaputin</code>, <code>/slavaukraine</code>, <code>/kurwa</code>, <code>/wh40k</code>, <code>/yer</code>, <code>/suka_blyat</code>, <code>/shiza</code>, <code>/gopnik</code>, <code>/matrix</code>, <code>/america</code>, <code>/holiday</code>, <code>/oldweb</code>, <code>/jewish</code>\n\n"
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
