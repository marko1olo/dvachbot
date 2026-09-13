# -*- coding: utf-8 -*-
"""
Unit tests for solo casino session watchdogs (roulette & blackjack session expiration).
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import casino_engine


class TestSoloCasinoWatchdogs:
    """Tests for expire_stale_roulette_sessions and expire_stale_bj_sessions."""

    def test_expire_stale_roulette_sessions(self):
        casino_engine.active_roulette_sessions.clear()

        # Session 1: Fresh (10 seconds old)
        casino_engine.active_roulette_sessions[101] = {
            "streak": 2,
            "bet": 500,
            "current_mult": 1.45,
            "last_shot": time.time() - 10.0,
            "board_id": "b",
            "chat_id": 101,
        }

        # Session 2: Stale (350 seconds old)
        casino_engine.active_roulette_sessions[102] = {
            "streak": 3,
            "bet": 1000,
            "current_mult": 2.10,
            "last_shot": time.time() - 350.0,
            "board_id": "b",
            "chat_id": 102,
        }

        expired = casino_engine.expire_stale_roulette_sessions(timeout_sec=300.0)

        assert len(expired) == 1
        user_id, session = expired[0]
        assert user_id == 102
        assert session["bet"] == 1000
        assert session["current_mult"] == 2.10

        # Fresh session remains active
        assert 101 in casino_engine.active_roulette_sessions
        assert 102 not in casino_engine.active_roulette_sessions

    def test_expire_stale_bj_sessions_auto_resolution(self):
        casino_engine.active_bj_sessions.clear()

        # Session 1: Fresh (50 seconds old)
        casino_engine.active_bj_sessions[201] = {
            "bet": 200,
            "deck": [("7", "♠"), ("8", "♥")],
            "player_hand": [("10", "♠"), ("9", "♦")],
            "dealer_hand": [("10", "♣"), ("6", "♠")],
            "created_at": time.time() - 50.0,
        }

        # Session 2: Stale (400 seconds old) - Player has 20, dealer will draw and bust (16 + 10 = 26)
        casino_engine.active_bj_sessions[202] = {
            "bet": 1000,
            "deck": [("5", "♠"), ("10", "♦")],  # pop() yields ("10", "♦") -> 16 + 10 = 26 (Bust)
            "player_hand": [("10", "♠"), ("K", "♥")],  # 20
            "dealer_hand": [("10", "♣"), ("6", "♠")],   # 16 -> hits
            "created_at": time.time() - 400.0,
        }

        resolved = casino_engine.expire_stale_bj_sessions(timeout_sec=300.0)

        assert len(resolved) == 1
        user_id, session, outcome, payout = resolved[0]
        assert user_id == 202
        assert outcome == "win"
        assert payout == 2000

        # Fresh session remains active
        assert 201 in casino_engine.active_bj_sessions
        assert 202 not in casino_engine.active_bj_sessions
