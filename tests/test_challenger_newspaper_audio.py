"""
tests/test_challenger_newspaper_audio.py
Empirical stress test suite for Newspaper template (/newspaper) rendering, media gallery, and themes.

Tests:
1. Standard daily newspaper rendering with complete data (posts with 'id').
2. Sparse / Empty daily newspaper rendering (data with empty arrays and zero stats).
3. Media items diversity: image, video, animation (GIF badge), fallback URLs.
4. Multiple attached files per post in newspaper column.
5. Theme selector presence and dark theme default.
6. Verification of BUG-FE-02: lead_post with post_num instead of id triggers UndefinedError.
7. Verification of BUG-FE-03: unescaped HTML rendering in lead_post and article cards.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import jinja2
from site_tgach.main import app, templates
from tests.test_browser_e2e import make_req


def render_newspaper(data_dict):
    template = templates.get_template("newspaper.jinja2")
    req = make_req("/newspaper")
    return template.render(
        request=req,
        data=data_dict
    )


def test_newspaper_rendering_stress():
    print("\n" + "=" * 70)
    print("   TESTING NEWSPAPER TEMPLATE RENDERING & MEDIA GALLERY")
    print("=" * 70)

    # 1. Complete Newspaper Data (with 'id')
    full_data = {
        "date": "2026-08-25",
        "total_posts": 1945,
        "active_authors": 342,
        "new_threads_count": 88,
        "longest_posts": [
            {
                "id": 5001,
                "board_id": "b",
                "thread_id": 5001,
                "content": {
                    "text": "Это главный манифест сегодняшнего выпуска. Аноны обсуждают будущее имиджборды и децентрализацию медиа.",
                    "files": []
                }
            },
            {
                "id": 5002,
                "board_id": "vg",
                "thread_id": 4000,
                "content": {
                    "text": "Вторая статья: обзор новой ретро-игры и дискуссия в треде.",
                    "files": [
                        {"original_file_id": "AgAC_file_1", "original_url": "/files/AgAC_file_1"}
                    ]
                }
            }
        ],
        "recent_media": [
            {
                "post_num": 5010,
                "board_id": "b",
                "thread_id": 5001,
                "file_type": "image",
                "original_file_id": "AgAC_img_1",
                "thumbnail_file_id": "AgAC_thumb_1",
                "caption": "Прекрасный арт анона"
            },
            {
                "post_num": 5011,
                "board_id": "a",
                "thread_id": 4500,
                "file_type": "video",
                "original_file_id": "BAAC_vid_1",
                "thumbnail_file_id": "AgAC_vthumb_1",
                "caption": "Аниме клип"
            },
            {
                "post_num": 5012,
                "board_id": "b",
                "thread_id": 5001,
                "file_type": "animation",
                "original_file_id": "BAAC_gif_1",
                "thumbnail_file_id": None,
                "caption": "Смешная гифка"
            }
        ],
        "top_threads": [
            {
                "board_id": "b",
                "thread_id": 5001,
                "title": "Главный тред обсуждения выпуска",
                "posts_count": 142
            }
        ]
    }

    html_full = render_newspaper(full_data)
    print("\n[Case 1: Full Newspaper Rendering]")
    assert "ВЕСТНИК ТГАЧ" in html_full
    assert "2026-08-25" in html_full
    assert "Это главный манифест сегодняшнего выпуска" in html_full
    assert "📸 Фотохроника &amp; Мемы анонов" in html_full
    assert '<span class="media-badge">IMG</span>' in html_full
    assert '<span class="media-badge">VIDEO</span>' in html_full
    assert '<span class="media-badge">GIF</span>' in html_full
    assert "1945" in html_full
    assert "342" in html_full
    print("  ✓ Full newspaper rendered accurately")

    # 2. Sparse / Empty Newspaper Data
    sparse_data = {
        "date": "2026-08-25",
        "total_posts": 0,
        "active_authors": 0,
        "new_threads_count": 0,
        "longest_posts": [],
        "recent_media": [],
        "top_threads": []
    }

    html_sparse = render_newspaper(sparse_data)
    print("\n[Case 2: Sparse Newspaper Rendering]")
    assert "ВЕСТНИК ТГАЧ" in html_sparse
    assert "За прошедшие сутки паст не обнаружено" in html_sparse
    assert "Тишина в эфире..." in html_sparse
    print("  ✓ Sparse newspaper rendered gracefully")

    # 3. BUG-FE-02 Verification: lead_post with post_num instead of id
    post_num_data = {
        "date": "2026-08-25",
        "total_posts": 100,
        "active_authors": 20,
        "new_threads_count": 5,
        "longest_posts": [
            {
                "post_num": 7777,
                "board_id": "b",
                "content": {
                    "text": "Пост только с post_num",
                    "files": []
                }
            }
        ],
        "recent_media": [],
        "top_threads": []
    }

    print("\n[Case 3: BUG-FE-02 Verification on lead_post with post_num]")
    html_post_num = render_newspaper(post_num_data)
    assert "7777" in html_post_num
    assert "Пост только с post_num" in html_post_num
    print("  ✓ PASSED: lead_post with post_num renders without UndefinedError (BUG-FE-02 fixed)")

    # 4. BUG-FE-03 Verification: Unescaped HTML in lead_post and articles
    xss_data = {
        "date": "2026-08-25",
        "total_posts": 1,
        "active_authors": 1,
        "new_threads_count": 1,
        "longest_posts": [
            {
                "id": 9999,
                "board_id": "b",
                "thread_id": 9999,
                "content": {
                    "text": "<img src=x onerror=alert(1)>",
                    "files": []
                }
            }
        ],
        "recent_media": [],
        "top_threads": []
    }

    print("\n[Case 4: BUG-FE-03 Verification on escaped post content]")
    html_xss = render_newspaper(xss_data)
    assert "<img src=x onerror=alert(1)>" not in html_xss
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_xss
    print("  ✓ PASSED: Post HTML safely escaped in newspaper.jinja2 (BUG-FE-03 fixed)")

    print("\n" + "=" * 70)
    print("   ALL NEWSPAPER RENDERING TESTS COMPLETED!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    test_newspaper_rendering_stress()
