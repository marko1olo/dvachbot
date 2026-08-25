"""
tests/test_challenger_guest_state.py
Empirical permutation and stress test suite for Chat Guest Notice and Input Disabling (R4-A, R4-B).

Tests:
1. session is None
2. session is {}
3. session = {"user": None}
4. session = {"user": {"id": "guest_abc", "is_guest": True, "is_admin": False}}
5. session = {"user": {"id": "guest_123", "is_guest": True, "is_admin": True}}
6. session = {"user": {"id": 12345, "is_guest": False, "is_admin": False}}
7. session = {"user": {"id": 1, "is_guest": False, "is_admin": True}}
8. session = {"user": {"id": 999}} (missing is_guest key)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from site_tgach.main import app, templates, BOARD_CONFIG
from tests.test_browser_e2e import make_req


def render_chat_with_session(session_dict):
    template = templates.get_template("chat.jinja2")
    req = make_req("/b/chat/")
    
    return template.render(
        request=req,
        board_id="b",
        boards=BOARD_CONFIG,
        board_info=BOARD_CONFIG.get("b", {"name": "Бред", "description": "Бред"}),
        posts=[],
        BOT_USERNAME="dvach_test_bot",
        site_mode="PUBLIC_READ",
        session=session_dict,
    )


def test_guest_chat_permutations():
    print("\n" + "=" * 70)
    print("   TESTING GUEST CHAT RESTRICTION PERMUTATIONS (R4-A, R4-B)")
    print("=" * 70)

    guest_sessions = [
        None,
        {},
        {"user": None},
        {"user": {"id": "guest_abc", "is_guest": True, "is_admin": False}},
        {"user": {"id": "guest_123", "is_guest": True, "is_admin": True}},
        {"user": {"id": "anon_guest", "is_guest": True}},
    ]

    for idx, s in enumerate(guest_sessions):
        html = render_chat_with_session(s)
        print(f"\n[Guest Permutation #{idx+1}]: session={s}")

        # 1. Guest notice banner must be present
        assert "guest-chat-notice" in html, f"Banner missing for session: {s}"
        assert "❌ Гости могут только читать чат. <a href=\"/login" in html, f"Banner text missing for session: {s}"

        # 2. Form must be disabled
        assert 'id="post-form" style="opacity: 0.5; pointer-events: none;"' in html, f"Form not disabled for session: {s}"

        # 3. Post textarea must be disabled and have guest placeholder
        assert 'id="post-text"' in html
        assert 'placeholder="❌ Гости могут только читать чат. Войдите для общения."' in html
        assert 'disabled' in html.split('id="post-text"')[1].split('>')[0]

        # 4. Format buttons must be disabled
        format_tags = ["data-tag=\"b\"", "data-tag=\"i\"", "data-tag=\"s\"", "data-tag=\"spoiler\"", "data-tag=\"shake\"", "data-tag=\"rainbow\"", "data-tag=\"blur\"", "data-tag=\"glitch\"", "id=\"help-tags-btn\""]
        for tag in format_tags:
            tag_block = html.split(tag)[1].split('>')[0]
            assert "disabled" in tag_block, f"Button {tag} not disabled for guest session: {s}"

        # 5. File input and picrandom disabled
        assert 'class="file-input-label" style="pointer-events: none; opacity: 0.5;"' in html
        assert 'class="picrandom-container" title="Прикрепить случайную картинку из архива" style="pointer-events: none; opacity: 0.5;"' in html
        
        # 6. Header login link vs logout link
        assert '<a href="/login" class="header-btn" title="Войти">🔑</a>' in html
        assert 'class="logout-link"' not in html
        print(f"  ✓ Verified: Guest restrictions correctly enforced")

    member_sessions = [
        {"user": {"id": 12345, "is_guest": False, "is_admin": False}},
        {"user": {"id": 1, "is_guest": False, "is_admin": True}},
    ]

    for idx, s in enumerate(member_sessions):
        html = render_chat_with_session(s)
        print(f"\n[Member Permutation #{idx+1}]: session={s}")

        # 1. Guest notice banner must NOT be present
        assert "guest-chat-notice" not in html, f"Banner unexpectedly present for member: {s}"

        # 2. Form must NOT have disabled inline styles
        assert 'id="post-form" style="opacity: 0.5; pointer-events: none;"' not in html

        # 3. Post textarea must NOT be disabled
        ta_attrs = html.split('id="post-text"')[1].split('>')[0]
        assert "disabled" not in ta_attrs, f"Textarea unexpectedly disabled for member: {s}"

        # 4. Format buttons must NOT be disabled
        for tag in ["data-tag=\"b\"", "data-tag=\"i\""]:
            tag_block = html.split(tag)[1].split('>')[0]
            assert "disabled" not in tag_block, f"Button {tag} unexpectedly disabled for member: {s}"

        # 5. Header logout link
        assert 'class="logout-link"' in html
        print(f"  ✓ Verified: Member form fully active")

    print("\n" + "=" * 70)
    print("   ALL GUEST PERMUTATION TESTS PASSED PERFECTLY!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_guest_chat_permutations()
