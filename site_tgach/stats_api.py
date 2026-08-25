# -*- coding: utf-8 -*-
"""
stats_api.py — FastAPI Standalone Endpoints for Next-Gen Stats WebApp & JSON API.
Provides /app/stats HTML view and /api/stats/* endpoints with in-memory caching.
"""

import os
import time
import json
import sqlite3
import contextlib
from typing import Dict, Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import numpy as np

import stats_v2

router = APIRouter(tags=["stats_v2"])

# In-memory cache for 30s
_DASHBOARD_CACHE: Dict[str, Any] = {}
_LAST_CACHE_TIME = 0.0

def connect_ro_db() -> sqlite3.Connection:
    conn = sqlite3.connect("file:dvach_bot.db?mode=ro", uri=True, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn

@router.get("/app/stats", response_class=HTMLResponse)
async def view_stats_dashboard(request: Request):
    """Renders the standalone interactive Telegram WebApp dashboard."""
    templates = request.app.state.templates if hasattr(request.app.state, "templates") else Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
    return templates.TemplateResponse(request=request, name="stats_dashboard.jinja2", context={"request": request})


@router.get("/api/stats/dashboard_data")
async def get_dashboard_data():
    """Returns cached JSON metrics for charts."""
    global _DASHBOARD_CACHE, _LAST_CACHE_TIME
    now = time.time()
    
    if _DASHBOARD_CACHE and (now - _LAST_CACHE_TIME < 30.0):
        return _DASHBOARD_CACHE

    day_ago = now - 86400
    with contextlib.closing(connect_ro_db()) as conn:
        c = conn.cursor()
        
        # 1. 24h Posts & Users
        c.execute("SELECT COUNT(*), COUNT(DISTINCT author_id) FROM Posts WHERE timestamp > ?", (day_ago,))
        row_24h = c.fetchone()
        posts_24h = row_24h[0] if row_24h else 0
        users_24h = row_24h[1] if row_24h else 0

        # 2. Hourly series
        c.execute("""
            SELECT cast(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as integer) as h,
                   COUNT(*) as cnt
            FROM Posts
            WHERE timestamp > ?
            GROUP BY h ORDER BY h
        """, (day_ago,))
        h_map = {r['h']: r['cnt'] for r in c.fetchall()}
        hourly_series = [h_map.get(h, 0) for h in range(24)]

        # 3. Top Boards
        c.execute("SELECT board_id, COUNT(*) as cnt FROM Posts WHERE timestamp > ? GROUP BY board_id ORDER BY cnt DESC LIMIT 5", (day_ago,))
        top_boards = [[r['board_id'], r['cnt']] for r in c.fetchall()]

        # 4. Economy Volume
        c.execute("SELECT COALESCE(SUM(ABS(amount)), 0) FROM UserTransactions WHERE timestamp > ?", (day_ago,))
        tx_vol = c.fetchone()[0] or 0

        # 5. Top Bayan
        c.execute("SELECT times FROM MediaReposts ORDER BY times DESC LIMIT 1")
        b_row = c.fetchone()
        top_bayan_times = b_row['times'] if b_row else 0

        # 6. Casino Net
        c.execute("""
            SELECT 
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as bets,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as wins
            FROM UserTransactions
            WHERE category = 'casino' OR description LIKE '%казино%'
        """)
        cas_row = c.fetchone()
        bets = cas_row['bets'] if cas_row and cas_row['bets'] is not None else 0
        wins = cas_row['wins'] if cas_row and cas_row['wins'] is not None else 0
        rake = max(0, bets - wins)

        # 7. Deciles
        c.execute("SELECT balance FROM Users WHERE balance >= 0 ORDER BY balance ASC")
        balances = [r['balance'] for r in c.fetchall()]
        deciles = []
        if balances:
            dec_chunks = np.array_split(balances, 10)
            total_w = max(1, sum(balances))
            deciles = [round(float(sum(ch) / total_w * 100), 1) for ch in dec_chunks]

        # 8. Media Formats
        c.execute("""
            SELECT 
                SUM(CASE WHEN content LIKE '%"type": "photo"%' THEN 1 ELSE 0 END) as photo,
                SUM(CASE WHEN content LIKE '%"type": "video"%' THEN 1 ELSE 0 END) as video,
                SUM(CASE WHEN content LIKE '%"type": "animation"%' THEN 1 ELSE 0 END) as gif,
                SUM(CASE WHEN content LIKE '%"type": "sticker"%' THEN 1 ELSE 0 END) as sticker
            FROM Posts WHERE timestamp > (strftime('%s', 'now') - 30 * 86400)
        """)
        m_row = c.fetchone()
        if m_row:
            media_formats = [m_row['photo'] or 0, m_row['video'] or 0, m_row['gif'] or 0, m_row['sticker'] or 0]
        else:
            media_formats = [0, 0, 0, 0]

    _DASHBOARD_CACHE = {
        "posts_24h": posts_24h,
        "users_24h": users_24h,
        "tx_volume": int(tx_vol),
        "top_bayan_times": top_bayan_times,
        "hourly_series": hourly_series,
        "top_boards": top_boards,
        "casino_wins": int(wins),
        "casino_rake": int(rake),
        "deciles": deciles,
        "media_formats": media_formats
    }
    _LAST_CACHE_TIME = now
    return _DASHBOARD_CACHE


@router.get("/api/stats/poster/{category}")
async def get_stats_poster(category: str):
    """Streams on-demand rendered HD poster PNG."""
    generators = {
        "economy": stats_v2.generate_economy_heists_poster,
        "pvp": stats_v2.generate_pvp_bioweapons_poster,
        "drama": stats_v2.generate_drama_beef_poster,
        "memes": stats_v2.generate_bayan_memetics_poster
    }
    if category not in generators:
        return Response(content="Category not found", status_code=404)

    buf = generators[category]()
    return StreamingResponse(buf, media_type="image/png")
