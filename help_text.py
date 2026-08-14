# help_text.py
import random

HELP_TEXT_COMMANDS = [
    (
        "⚡ <b>ТГАЧ /b/ — Навигация и Список Команд</b>\n\n"
        "Канал архива: https://t.me/tgach_archive\n"
        "Доски: /b /po /a /vg /sex /int /trash\n\n"
        "<b>🛠 Основное общение:</b>\n"
        "• Чтобы написать пост — просто отправь текст/медиа боту.\n"
        "• Чтобы ответить — сделай <b>Reply (Ответить)</b> на сообщение.\n"
        "• /redact — Удалить свой последний пост (реплаем)\n"
        "• /whisper &lt;текст&gt; — Анонимный шёпот автору поста\n"
        "• /poll вопрос | вариант 1 | вариант 2 — Создать опрос\n"
        "• /report — Пожаловаться модераторам на вайп/спам\n\n"
        "<b>💰 Экономика и Шекели:</b>\n"
        "• Ставь реакции: 👍 лайк (+12₽ автору), 👎 сажа (-5.5₽ штраф)\n"
        "• /wallet — Твой кошелек и баланс шекелей\n"
        "• /work (/earn, /bomj) — Заработок (бутылки / продать мать)\n"
        "• /daily (/bonus) — Ежедневный бонус (+75₽ + серия дней)\n"
        "• /shop (/market) — Теневой рынок (шапочки, пушки, щиты)\n"
        "• /top (/leaders) — Рейтинг богатейших анонов борды\n"
        "• /rob — Ограбить анона на 10-30% баланса (реплаем)\n"
        "• /shit — Запустить говном в автора поста (реплаем)\n"
        "• /curse — Наложить проклятие на посты жертвы (реплаем)\n"
        "• /partyvan — Вызвать пативэн и посадить в КПЗ (реплаем)\n"
        "• /duel — Вызвать на дуэль на шекели (реплаем)\n\n"
        "<b>🖼 Медиа, Инвайты и Демотиваторы:</b>\n"
        "• /dem заголовок | подпись — Демотиватор (реплаем на фото)\n"
        "• /invite_pic — Графический постер с QR-кодом (7 стилей)\n"
        "• /invite — Текстовые фразы для инвайта друзей\n"
        "• /fap /hent /nsfw [число] — Случайный аниме-арт\n"
        "• /loli [число] — Лоликон-арт\n"
        "• /roll — Случайное число (0-100)\n"
        "• /ruletka — Случайный тред\n\n"
        "<b>🧠 Нейросети и Аналитика:</b>\n"
        "• /summarize — ИИ-пересказ последних событий чата\n"
        "• /roast — Жесткая ИИ-прожарка срачей на доске\n"
        "• /stats (/activity) — Графики активности доски\n"
        "• /tags — Облако популярных тем и тегов\n"
        "• /me (/profile) — Твой паспорт и личная статистика\n\n"
        "<b>🎭 Режимы общения (на 5 минут):</b>\n"
        "🌸 /anime | 🇷🇺 /zaputin | 🇺🇦 /slavaukraine | 🇵🇱 /polish\n"
        "⚔️ /warhammer | 📜 /imperial | 👊 /gopnik | 🧠 /schizo\n"
        "🐊 /rus | 🐒 /abu | 🕶 /matrix | 📟 /oldweb | ✡️ /jewish | 🦅 /america | 🎄 /holiday"
    )
]

HELP_TEXT_EN_COMMANDS = [
    (
        "⚡ <b>TGACH /b/ — Command Navigation Index</b>\n\n"
        "Archive Channel: https://t.me/tgach_archive\n"
        "Boards: /b /po /a /vg /sex /int /trash\n\n"
        "<b>🛠 Core Features:</b>\n"
        "• Send any text or photo to post anonymously on the board.\n"
        "• <b>Reply</b> to any message to send an anonymous answer.\n"
        "• /redact — Delete your post (as reply)\n"
        "• /whisper &lt;text&gt; — Secret whisper to post author\n"
        "• /poll topic | opt1 | opt2 — Create a poll\n"
        "• /report — Report wipe/spam to moderators\n\n"
        "<b>💰 Economy & Shekels:</b>\n"
        "• Reactions: 👍 like (+12 RUB to author), 👎 sage (-5.5 RUB penalty)\n"
        "• /wallet — Balance & withdrawal\n"
        "• /work (/earn) — Jobs (recycle bottles / sell mother)\n"
        "• /daily — Daily bonus streak (+75 RUB)\n"
        "• /shop — Black Market (tin foil hats, guns, shields)\n"
        "• /top — Richest anons leaderboard\n"
        "• /rob — Rob 10-30% of target balance (reply)\n"
        "• /shit — Throw feces at post author (reply)\n"
        "• /curse — Hex victim posts with speech styles (reply)\n"
        "• /partyvan — Send target to jail (reply)\n"
        "• /duel — Challenge an anon to a shekel duel (reply)\n\n"
        "<b>🖼 Media, Invites & Demotivators:</b>\n"
        "• /dem title | subline — Demotivator poster (reply to photo)\n"
        "• /invite_pic — Graphic QR invite card (7 visual styles)\n"
        "• /invite — Text invite generator\n"
        "• /fap /hent /nsfw [N] — Random anime art\n"
        "• /loli [N] — Lolicon art\n"
        "• /roll — Random roll (0-100)\n"
        "• /ruletka — Random thread\n\n"
        "<b>🧠 AI & Analytics:</b>\n"
        "• /summarize — AI chat summary\n"
        "• /roast — Brutal AI roast of board debates\n"
        "• /stats — Activity charts\n"
        "• /tags — Trending word cloud\n"
        "• /me — Anon passport & stats\n\n"
        "<b>🎭 Speech Modes (5 min):</b>\n"
        "🌸 /anime | 🇷🇺 /zaputin | 🇺🇦 /slavaukraine | 🇵🇱 /polish\n"
        "⚔️ /warhammer | 📜 /imperial | 👊 /gopnik | 🧠 /schizo\n"
        "🐊 /rus | 🐒 /abu | 🕶 /matrix | 📟 /oldweb | ✡️ /jewish | 🦅 /america | 🎄 /holiday"
    )
]

HELP_TEXT_JP_COMMANDS = [
    (
        "⚡ <b>TGACH /b/ — コマンド一覧</b>\n\n"
        "アーカイブ: https://t.me/tgach_archive\n"
        "板一覧: /b /po /a /vg /sex /int /trash\n\n"
        "<b>🛠 基本機能:</b>\n"
        "• メッセージを送信すると匿名で投稿されます。\n"
        "• <b>返信 (Reply)</b> で他のアノンにアンカーを付けます。\n"
        "• /redact — 自分の投稿を削除 (返信)\n"
        "• /poll お題 | 選択肢1 | 選択肢2 — 投票作成\n"
        "• /report — モデレーターに通報\n\n"
        "<b>💰 経済・シェケル:</b>\n"
        "• リアクション: 👍 いいね (+12 RUB), 👎 低評価 (-5.5 RUB)\n"
        "• /wallet — 残高と引き出し\n"
        "• /work — アルバイト (空き瓶拾い等)\n"
        "• /daily — デイリーボーナス (+75 RUB)\n"
        "• /shop — 闇市 (アルミホイル帽子、銃、盾)\n"
        "• /top — 富豪ランキング\n"
        "• /duel — 決闘を申し込む (返信)\n\n"
        "<b>🖼 メディア & 招待状:</b>\n"
        "• /dem タイトル | サブ — デモティベーター作成\n"
        "• /invite_pic — QRコード付き招待画像 (7スタイル)\n"
        "• /fap /hent /loli — アニメアート\n"
        "• /summarize — AIチャット要約\n"
        "• /roast — AI煽り要約\n"
        "• /me — プロフィール\n\n"
        "<b>🎭 特殊モード:</b>\n"
        "🌸 /anime | 🇷🇺 /zaputin | ⚔️ /warhammer | 👊 /gopnik | 🧠 /schizo | 🐊 /rus | 🐒 /abu | 🕶 /matrix"
    )
]

THREAD_PROMO_TEXT_RU = [
    "📌 <b>Хочешь создать свой тред?</b>\nПиши <code>/create Название треда</code> на тематических досках (/po /a /vg /sex /trash)!",
    "💡 <b>Обсуждай только интересное:</b>\nИспользуй <code>/threads</code> для просмотра каталога активных тредов."
]

THREAD_PROMO_TEXT_EN = [
    "📌 <b>Want to create a thread?</b>\nType <code>/create Thread Title</code> on boards (/po /a /vg /sex /trash)!",
    "💡 <b>Browse active threads:</b>\nUse <code>/threads</code> to view the board catalog."
]

THREAD_PROMO_TEXT_JP = [
    "📌 <b>スレッドを立てる:</b>\n<code>/create スレタイ</code> で新規スレを作成できます！",
    "💡 <b>スレッド一覧:</b>\n<code>/threads</code> でカタログを確認できます。"
]

MODE_INFO_TEXT_RU = [
    "🎭 <b>Режимы общения:</b>\nВключи временный режим на 5 минут: /anime, /zaputin, /slavaukraine, /polish, /warhammer, /imperial, /gopnik, /schizo, /rus, /abu, /matrix, /oldweb, /jewish, /america, /holiday!"
]

MODE_INFO_TEXT_EN = [
    "🎭 <b>Chat Modes:</b>\nActivate a 5-minute speech style: /anime, /zaputin, /slavaukraine, /polish, /warhammer, /imperial, /gopnik, /schizo, /rus, /abu, /matrix, /oldweb, /jewish, /america, /holiday!"
]

MODE_INFO_TEXT_JP = [
    "🎭 <b>チャットモード:</b>\n5分間スタイル変更: /anime, /zaputin, /slavaukraine, /polish, /warhammer, /imperial, /gopnik, /schizo, /rus, /abu, /matrix!"
]

MECHANICS_INFO_TEXT_RU = [
    "💡 <b>Лайфхак:</b>\nСтавь реакции на посты других анонов — автор получит уведомление и шекели!"
]

MECHANICS_INFO_TEXT_EN = [
    "💡 <b>Pro-Tip:</b>\nReact to other posts with emojis — authors receive anonymous notifications and shekels!"
]

MECHANICS_INFO_TEXT_JP = [
    "💡 <b>ヒント:</b>\nリアクションを付けると投稿者に匿名通知とシェケルが届きます！"
]

CHANNEL_PROMO_TEXT_RU = [
    "📢 <b>Канал Архива:</b> https://t.me/tgach_archive\nЗдесь сохраняются все посты и медиа со всех досок!"
]

CHANNEL_PROMO_TEXT_EN = [
    "📢 <b>Archive Channel:</b> https://t.me/tgach_archive\nAll posts and media are mirrored in real time!"
]

CHANNEL_PROMO_TEXT_JP = [
    "📢 <b>アーカイブチャンネル:</b> https://t.me/tgach_archive\n全投稿がリアルタイムでミラーリングされます。"
]

def generate_boards_list(board_config: dict, lang: str = "ru") -> str:
    lines = ["📋 <b>Список доступных досок:</b>\n" if lang == "ru" else ("📋 <b>Available Boards:</b>\n" if lang == "en" else "📋 <b>利用可能な板:</b>\n")]
    for b_id, b_info in board_config.items():
        if b_id in ["test"]: continue
        b_name = b_info.get("name", b_id)
        b_desc = b_info.get("description", "")
        lines.append(f"• <b>/{b_id}</b> — {b_name} <i>({b_desc})</i>")
    return "\n".join(lines)
