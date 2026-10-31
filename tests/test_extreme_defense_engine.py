import pytest
import asyncio
import time
import json
from unittest import mock
from aiogram import types

from extreme_defense_engine import (
    classify_extreme_media,
    register_extreme_strike,
    execute_extreme_lockdown,
    process_file_extreme_defense,
    _EXTREME_STRIKES_CACHE
)

def test_classify_copro():
    # Definite copro
    assert classify_extreme_media("1boy, solo, nudity, penis, feces, scat, mud, masturbation")[0] is True
    assert classify_extreme_media("photo, coprophilia, disgusting, shock")[0] is True
    assert classify_extreme_media("feces, human, defecation, anal")[0] is True

    # Safe / False positive resistance
    assert classify_extreme_media("jazz, scat, singing, vocal, performance")[0] is False
    assert classify_extreme_media("wildlife, nature, animal, dirt, feces, outdoors")[0] is False
    assert classify_extreme_media("toilet, coffee, mug, humor, joke, meme")[0] is False

def test_classify_guro():
    # Definite guro / extreme gore
    assert classify_extreme_media("anime, guro, blood, dark, horror")[0] is True
    assert classify_extreme_media("snuff, crime, torture")[0] is True
    assert classify_extreme_media("dismemberment, severed_head, crime")[0] is True
    assert classify_extreme_media("photo, real_life, gore, wound, corpse, hospital")[0] is True

    # Safe / Anime action / Ecchi
    assert classify_extreme_media("anime, 1boy, action, battle, sword, blood, injury")[0] is False
    assert classify_extreme_media("1girl, solo, anime, bikini, breasts, smile")[0] is False
    assert classify_extreme_media("1girl, 1boy, hentai, nude, sex, missionary, cum")[0] is False
    assert classify_extreme_media("cosplay, halloween, costume, jason_voorhees, fake_blood, mask")[0] is False

@pytest.mark.asyncio
async def test_strike_accumulation_and_lockdown(isolated_test_db):
    db = isolated_test_db
    author_id = 99887766
    board_id = 'b'

    # Insert user into isolated DB
    await db.execute(
        "INSERT INTO Users (user_id, board_id, role, shadow_ban_media) VALUES (?, ?, 'user', 0)",
        (author_id, board_id)
    )
    # Insert two posts by this user
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7001, 'b', ?, ?, '{\"type\": \"photo\"}')",
        (author_id, time.time() - 100)
    )
    await db.execute(
        "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (7001, 'photo', 'file_bad_1')"
    )
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (7002, 'b', ?, ?, '{\"type\": \"photo\"}')",
        (author_id, time.time() - 50)
    )
    await db.execute(
        "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (7002, 'photo', 'file_bad_2')"
    )
    await db.commit()

    # Clear memory cache for author
    _EXTREME_STRIKES_CACHE.pop(author_id, None)

    bot_mock = mock.AsyncMock()
    bot_mock.send_message = mock.AsyncMock()

    # Strike 1: First bad media
    res1 = await process_file_extreme_defense(
        bot=bot_mock,
        file_id='file_bad_1',
        tags='1boy, adult, nudity, feces, scat, mud, masturbation',
        description='copro',
        post_num=7001,
        author_id=author_id,
        board_id=board_id
    )
    assert res1 is True

    # User should NOT be locked down yet on Strike 1
    async with db.execute("SELECT shadow_ban_media FROM Users WHERE user_id = ?", (author_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 0  # not yet banned

    # Strike 2: Second bad media
    res2 = await process_file_extreme_defense(
        bot=bot_mock,
        file_id='file_bad_2',
        tags='anime, guro, dismemberment, horror',
        description='guro',
        post_num=7002,
        author_id=author_id,
        board_id=board_id
    )
    assert res2 is True

    # On Strike >= 2, lockdown MUST be triggered:
    # 1. shadow_ban_media == 1
    async with db.execute("SELECT shadow_ban_media FROM Users WHERE user_id = ?", (author_id,)) as cur:
        row = await cur.fetchone()
        assert row[0] == 1  # Media toggle banned!

    # 2. Shadowmute recorded in Mutes
    async with db.execute("SELECT COUNT(*) FROM Mutes WHERE user_id = ? AND mute_type = 'shadow'", (author_id,)) as cur:
        mutes_count = (await cur.fetchone())[0]
        assert mutes_count >= 1

@pytest.mark.asyncio
async def test_delete_user_posts_foreign_key_safety(isolated_test_db):
    """
    Верифицирует, что delete_user_posts удаляет посты с PostFiles, PostCopies,
    ChannelCopies и т.д. БЕЗ ошибки FOREIGN KEY constraint failed.
    """
    import main
    from main import delete_user_posts

    db = isolated_test_db
    author_id = 11223344
    board_id = 'b'

    # Создаем посты и привязанные дочерние записи
    for p_num in [8001, 8002]:
        await db.execute(
            "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (?, 'b', ?, ?, '{}')",
            (p_num, author_id, time.time() - 60)
        )
        await db.execute(
            "INSERT INTO PostFiles (post_num, file_type, original_file_id) VALUES (?, 'photo', ?)",
            (p_num, f"fid_{p_num}")
        )
        await db.execute(
            "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (?, 999, ?)",
            (p_num, p_num + 1000)
        )
        await db.execute(
            "INSERT INTO ChannelCopies (post_num, channel_id, message_id) VALUES (?, -100123, ?)",
            (p_num, p_num + 2000)
        )
        await db.execute(
            "INSERT INTO BroadcastQueue (post_num, created_at) VALUES (?, ?)",
            (p_num, time.time())
        )
    await db.commit()

    bot_mock = mock.AsyncMock()

    # Удаляем посты за 60 минут с замоканным get_pool
    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        deleted_count = await delete_user_posts(bot_mock, author_id, 60, board_id)
        assert deleted_count == 2

    # Проверяем, что в базе всё вычищено
    async with db.execute("SELECT COUNT(*) FROM Posts WHERE author_id = ?", (author_id,)) as cur:
        assert (await cur.fetchone())[0] == 0

    async with db.execute("SELECT COUNT(*) FROM PostFiles WHERE post_num IN (8001, 8002)") as cur:
        assert (await cur.fetchone())[0] == 0

@pytest.mark.asyncio
async def test_cmd_wipe_routing(isolated_test_db):
    """
    Проверяет, что /wipe работает для админа даже если board_id=None (в ЛС бота)
    и корректно разрешает board_id и автора из номера поста.
    """
    import main
    from main import cmd_wipe
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    # Создаем пост в isolated_test_db
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content) VALUES (9001, 'b', 55555, ?, '{}')",
        (time.time(),)
    )
    await db.commit()

    msg = mock.AsyncMock(spec=types.Message)
    msg.from_user = mock.MagicMock(id=admin_id)
    msg.reply_to_message = None
    msg.text = "/wipe 9001 30m"
    msg.caption = None
    msg.answer = mock.AsyncMock()
    msg.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        # Вызываем с board_id=None (как в ЛС)
        await cmd_wipe(msg, board_id=None, stream='ru')

    assert msg.answer.called
    reply_args = msg.answer.call_args[0][0]
    # Должен сформировать подтверждение вайпа на /b/ с кнопками
    assert "Вайп:" in reply_args or "Wipe" in reply_args
    assert "/b/" in reply_args

@pytest.mark.asyncio
async def test_cmd_sdel_routing(isolated_test_db):
    """
    Проверяет, что /sdel работает по номеру поста без обязательного reply
    и для админа при board_id=None.
    """
    import main
    from main import cmd_sdel
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, timestamp, content, is_shadow) VALUES (9002, 'b', 66666, ?, '{}', 0)",
        (time.time(),)
    )
    await db.execute(
        "INSERT INTO PostCopies (post_num, recipient_id, message_id) VALUES (9002, 77777, 100)",
    )
    await db.commit()

    msg = mock.AsyncMock(spec=types.Message)
    msg.from_user = mock.MagicMock(id=admin_id)
    msg.reply_to_message = None
    msg.text = "/sdel 9002"
    msg.caption = None
    msg.answer = mock.AsyncMock()
    msg.delete = mock.AsyncMock()
    msg.bot = mock.AsyncMock()
    msg.bot.delete_message = mock.AsyncMock(return_value=True)

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_sdel(msg, board_id=None, stream='ru')

    assert msg.answer.called
    # В БД пост должен стать is_shadow=1
    async with db.execute("SELECT is_shadow FROM Posts WHERE post_num = 9002") as cur:
        row = await cur.fetchone()
        assert row[0] == 1

@pytest.mark.asyncio
async def test_admin_commands_pm_safety(isolated_test_db):
    """
    Проверяет, что команды админа (/whois, /gunban, /lockdown) не падают
    и не блокируются, когда админ вызывает их в ЛС (board_id=None).
    """
    import main
    from main import cmd_whois, cmd_gunban, cmd_bot_lockdown
    from common.config import ADMIN_IDS

    db = isolated_test_db
    admin_id = next(iter(ADMIN_IDS))

    # /whois in PM
    msg_whois = mock.AsyncMock(spec=types.Message)
    msg_whois.from_user = mock.MagicMock(id=admin_id)
    msg_whois.reply_to_message = None
    msg_whois.text = "/whois 12345"
    msg_whois.caption = None
    msg_whois.answer = mock.AsyncMock()
    msg_whois.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_whois(msg_whois, board_id=None, stream='ru')
    assert msg_whois.answer.called

    # /gunban in PM
    msg_gunban = mock.AsyncMock(spec=types.Message)
    msg_gunban.from_user = mock.MagicMock(id=admin_id)
    msg_gunban.reply_to_message = None
    msg_gunban.text = "/gunban 12345"
    msg_gunban.caption = None
    status_mock = mock.AsyncMock()
    msg_gunban.answer = mock.AsyncMock(return_value=status_mock)
    msg_gunban.delete = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_gunban(msg_gunban, board_id=None, stream='ru')
    assert msg_gunban.answer.called

    # /lockdown in PM
    msg_lock = mock.AsyncMock(spec=types.Message)
    msg_lock.from_user = mock.MagicMock(id=admin_id)
    msg_lock.text = "/lockdown on"
    msg_lock.caption = None
    msg_lock.answer = mock.AsyncMock()

    with mock.patch.object(main, "get_pool", mock.AsyncMock(return_value=db)):
        await cmd_bot_lockdown(msg_lock, board_id=None)
    assert msg_lock.answer.called
    assert "активирован" in msg_lock.answer.call_args[0][0]
