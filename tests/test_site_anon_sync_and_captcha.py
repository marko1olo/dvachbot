# -*- coding: utf-8 -*-
import pytest
from common.anon_identity import generate_anon_name
from site_tgach.main import (
    _convert_and_enrich_posts,
    nick_from_hash,
    to_makaba_post,
    verify_captcha_solution,
    safe_user_hash,
    _HASH_TO_ANON_NAME,
)


def test_anon_identity_sync_between_bot_and_site():
    """
    Verifies that the anon identity calculated on the site matches
    the Telegram bot's canonical anon name 100%, without double-hashing
    the 12-char hex safe_user_hash.
    """
    test_uids = [6557599214, 123456789, 987654321, 42, 1000000001]

    for uid in test_uids:
        bot_name_ru = generate_anon_name(uid, stream="ru")
        expected_masked_hash = safe_user_hash(uid)

        raw_post = {
            "post_num": 100 + (uid % 1000),
            "board_id": "b",
            "author_id": uid,
            "content": {"text": f"Test post from {uid}", "type": "text"},
            "timestamp": 1700000000,
        }

        enriched_posts = _convert_and_enrich_posts([raw_post])
        post = enriched_posts[0]

        # 1. Post anon_name on site must match bot canonical name
        assert post["anon_name"] == bot_name_ru, (
            f"UID {uid}: Site anon_name '{post['anon_name']}' != Bot canonical '{bot_name_ru}'"
        )

        # 2. Post author_id must be safely masked with safe_user_hash
        assert post["author_id"] == expected_masked_hash
        assert len(post["author_id"]) == 12

        # 3. Jinja template filter nick_from_hash on masked author_id must return canonical name
        rendered_nick = nick_from_hash(post["author_id"], stream="ru")
        assert rendered_nick == bot_name_ru, (
            f"UID {uid}: nick_from_hash('{post['author_id']}') returned '{rendered_nick}', expected '{bot_name_ru}'"
        )

        # 4. Makaba export to_makaba_post must return canonical name
        makaba = to_makaba_post(post, "b")
        assert makaba["name"] == bot_name_ru, (
            f"UID {uid}: to_makaba_post['name'] '{makaba['name']}' != '{bot_name_ru}'"
        )


def test_anon_identity_idempotency():
    """
    Verifies that running _convert_and_enrich_posts multiple times
    is strictly idempotent and does not corrupt or re-hash author_id / anon_name.
    """
    uid = 6557599214
    bot_name = generate_anon_name(uid, stream="ru")
    post = {
        "post_num": 555,
        "board_id": "b",
        "author_id": uid,
        "content": {"text": "Idempotency check", "type": "text"},
        "timestamp": 1700000000,
    }

    first_pass = _convert_and_enrich_posts([post])[0]
    author_hash_1 = first_pass["author_id"]
    anon_name_1 = first_pass["anon_name"]

    assert anon_name_1 == bot_name
    assert author_hash_1 == safe_user_hash(uid)

    # Second pass on the already enriched post
    second_pass = _convert_and_enrich_posts([first_pass])[0]
    assert second_pass["author_id"] == author_hash_1
    assert second_pass["anon_name"] == anon_name_1


def test_verify_captcha_solution_all_modes():
    """
    Verifies captcha verification logic for all supported modes,
    especially 'major' and 'protocol' which previously caused loop lockouts.
    """
    # 1. Major mode (FSB denunciation)
    major_session = {"mode": "major"}
    assert verify_captcha_solution(major_session, "denounced") is True
    assert verify_captcha_solution(major_session, "DENOUNCED") is True
    assert verify_captcha_solution(major_session, "invalid") is False
    assert verify_captcha_solution(major_session, None) is False

    # 2. Protocol mode (interrogation confession or silence)
    protocol_session = {"mode": "protocol"}
    assert verify_captcha_solution(protocol_session, "confessed") is True
    assert verify_captcha_solution(protocol_session, "silent_consent") is True
    assert verify_captcha_solution(protocol_session, "CONFESSED") is True
    assert verify_captcha_solution(protocol_session, "refused") is False
    assert verify_captcha_solution(protocol_session, None) is False

    # 3. Can mode
    can_session = {"mode": "can"}
    assert verify_captcha_solution(can_session, "opened") is True
    assert verify_captcha_solution(can_session, "closed") is False

    # 4. Math mode
    math_session = {"mode": "math", "answer": 42}
    assert verify_captcha_solution(math_session, "42") is True
    assert verify_captcha_solution(math_session, "41") is False

    # 5. Monkey mode
    monkey_session = {"mode": "monkey", "target_x": 100, "target_y": 150}
    assert verify_captcha_solution(monkey_session, None, captcha_x=105, captcha_y=145) is True
    assert verify_captcha_solution(monkey_session, None, captcha_x=130, captcha_y=150) is False

    # 6. Bottle mode
    bottle_session = {"mode": "bottle", "start_angle": 180}
    # final_angle = (180 + 175) % 360 = 355 (> 345) -> valid
    assert verify_captcha_solution(bottle_session, "175") is True
    # final_angle = (180 + 0) = 180 -> invalid
    assert verify_captcha_solution(bottle_session, "0") is False

    # 7. Word mode
    word_session = {"mode": "word", "word": "АБУ"}
    assert verify_captcha_solution(word_session, "АБУ") is True
    assert verify_captcha_solution(word_session, "ЛОХ") is False

    # 8. Escobar / Fan / Spank modes
    for m in ("escobar", "fan", "spank"):
        sess = {"mode": m}
        assert verify_captcha_solution(sess, "success") is True
        assert verify_captcha_solution(sess, "failed") is False


def test_main_js_captcha_lockout_fixes():
    """
    Verifies that site_tgach/static/js/main.js has:
    1. isSolved flag in CaptchaManager.
    2. Unlock verification in moveTo using isSolved.
    3. Conditional CaptchaManager.reset() only on captcha-specific errors (no endless loops).
    """
    with open("site_tgach/static/js/main.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "isSolved: false" in js, "CaptchaManager missing isSolved state property"
    assert "this.isSolved || container.classList.contains('captcha-hidden')" in js, (
        "CaptchaManager.moveTo must check this.isSolved to prevent re-locking submit button"
    )
    assert "isCaptchaErr = (xhr.status === 400 || xhr.status === 403) && /captcha|капч|cap_|pow/i.test(errorMsg)" in js, (
        "Form submission error handler must only reset captcha when error is captcha-related"
    )


def test_anon_identity_stream_en():
    """
    Verifies that EN stream posts produce English transliterated anon names.
    """
    uid = 6557599214
    bot_name_en = generate_anon_name(uid, stream="en")
    post = {
        "post_num": 777,
        "board_id": "int",
        "author_id": uid,
        "stream": "en",
        "content": {"text": "Hello world", "type": "text"},
        "timestamp": 1700000000,
    }

    enriched = _convert_and_enrich_posts([post])[0]
    assert enriched["anon_name"] == bot_name_en
    assert nick_from_hash(enriched["author_id"], stream="en") == bot_name_en
    assert to_makaba_post(enriched, "int")["name"] == bot_name_en


def test_guest_chat_rejection_code_structure():
    """
    Verifies that api_create_post in site_tgach/main.py checks
    is_guest and post_mode == 'chat_post' before captcha/pow validation.
    """
    with open("site_tgach/main.py", "r", encoding="utf-8") as f:
        src = f.read()

    guest_check_pos = src.find('if is_guest and post_mode == "chat_post":')
    captcha_check_pos = src.find('global_captcha = (await get_system_setting("captcha_enabled")) == "true"')

    assert guest_check_pos != -1, "Guest chat check not found in main.py"
    assert captcha_check_pos != -1, "Captcha check not found in main.py"
    assert guest_check_pos < captcha_check_pos, (
        "Guest chat check must execute BEFORE captcha validation to prevent guest captcha loop trap"
    )

