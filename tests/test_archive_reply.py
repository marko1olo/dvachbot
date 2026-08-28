# -*- coding: utf-8 -*-
import pytest
from handlers.message_router import resolve_archive_or_inline_reply


@pytest.mark.asyncio
async def test_resolve_archive_or_inline_reply_formats(isolated_test_db):
    db = isolated_test_db
    import time, json
    await db.execute(
        "INSERT INTO Posts (post_num, board_id, author_id, content, timestamp) VALUES (501707, 'b', 123, ?, ?)",
        (json.dumps({'type': 'text', 'text': 'Original post'}), time.time())
    )

    # 1. Non-matching regular text
    pnum, cleaned = await resolve_archive_or_inline_reply("обычный текст без реплая")
    assert pnum is None
    assert cleaned == "обычный текст без реплая"

    # 2. >>post_num format
    pnum, cleaned = await resolve_archive_or_inline_reply(">>501707\nответ на пост")
    assert pnum == 501707
    assert cleaned == "ответ на пост"

    # 3. #post_num format
    pnum, cleaned = await resolve_archive_or_inline_reply("#501707\nответ")
    assert pnum == 501707
    assert cleaned == "ответ"

    # 4. t.me/tgchan_archive/post_num format
    pnum, cleaned = await resolve_archive_or_inline_reply("https://t.me/tgchan_archive/501707\nтекст реплая")
    assert pnum == 501707
    assert cleaned == "текст реплая"

    # 5. tgach.top link format
    pnum, cleaned = await resolve_archive_or_inline_reply("https://tgach.top/b/res/501707.html#post-501707\nкомментарий")
    assert pnum == 501707
    assert cleaned == "комментарий"
