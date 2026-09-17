import sys
import unittest.mock
import pytest

mock_modules = {
    'stats_generator': unittest.mock.MagicMock(),
    'common': unittest.mock.MagicMock(),
    'common.anon_identity': unittest.mock.MagicMock(),
    'common.text_utils': unittest.mock.MagicMock()
}

with unittest.mock.patch.dict('sys.modules', mock_modules):
    from leaderboard_card import draw_leaderboard_card, LeaderboardData, LeaderboardEntry

def test_draw_leaderboard_card_balance():
    data = LeaderboardData(
        board_id="b", mode="balance", mode_title="top", unit="sh",
        entries=[
            LeaderboardEntry(user_id=1, rank=1, anon_tag="Anon 1", custom_prefix="P1", value=100, is_caller=True),
            LeaderboardEntry(user_id=2, rank=2, anon_tag="Anon 2", custom_prefix=None, value=50, is_caller=False),
        ], caller_id=1, caller_rank=1, caller_value=100,
        total_users=2, total_metric=150
    )
    buf = draw_leaderboard_card(data)
    assert buf is not None
    assert buf.getvalue().startswith(b'\x89PNG')

def test_draw_leaderboard_card_posts():
    data = LeaderboardData(
        board_id="b", mode="posts", mode_title="top", unit="sh",
        entries=[], caller_id=0, caller_rank=0, caller_value=0,
        total_users=0, total_metric=0
    )
    buf = draw_leaderboard_card(data)
    assert buf is not None
    assert buf.getvalue().startswith(b'\x89PNG')

def test_draw_leaderboard_card_music():
    data = LeaderboardData(
        board_id="b", mode="music", mode_title="top", unit="sh",
        entries=[], caller_id=0, caller_rank=0, caller_value=0,
        total_users=0, total_metric=0
    )
    buf = draw_leaderboard_card(data)
    assert buf is not None
    assert buf.getvalue().startswith(b'\x89PNG')

def test_draw_leaderboard_card_reactions():
    data = LeaderboardData(
        board_id="b", mode="reactions", mode_title="top", unit="sh",
        entries=[], caller_id=0, caller_rank=0, caller_value=0,
        total_users=0, total_metric=0
    )
    buf = draw_leaderboard_card(data)
    assert buf is not None
    assert buf.getvalue().startswith(b'\x89PNG')
