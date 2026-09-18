import pytest
from site_tgach.main import _convert_and_enrich_posts

def test_convert_and_enrich_posts_handles_none_text():
    """Verify _convert_and_enrich_posts never crashes when content['text'] is None."""
    posts = [
        {
            "post_num": 100,
            "board_id": "b",
            "content": {"text": None, "type": "photo"}
        },
        {
            "post_num": 101,
            "board_id": "b",
            "content": {"text": None}
        },
        {
            "post_num": 102,
            "board_id": "b",
            "content": {"text": None, "type": "poll"}
        },
        {
            "post_num": 103,
            "board_id": "b",
            "content": {}
        },
        {
            "post_num": 104,
            "board_id": "b",
            "content": None
        },
        {
            "post_num": 105,
            "board_id": "b",
            "content": '{"text": null, "type": "video"}'
        }
    ]

    enriched = _convert_and_enrich_posts(posts)
    assert len(enriched) == 6
    for p in enriched:
        assert isinstance(p["content"]["text"], str)
        assert p["id"] in [100, 101, 102, 103, 104, 105]

    # Verify standard text post works normally
    normal = _convert_and_enrich_posts([{
        "post_num": 106,
        "board_id": "b",
        "content": {"text": "Нормальный текст поста", "type": "text"}
    }])
    assert normal[0]["content"]["text"] == "Нормальный текст поста"
    assert normal[0]["content"]["type"] == "text"
