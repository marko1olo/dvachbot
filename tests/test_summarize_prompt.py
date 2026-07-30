import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_get_summarize_prompt_and_chunk_ru_board():
    from main import _get_summarize_prompt_and_chunk
    with patch("main.get_board_chunk", new_callable=AsyncMock) as mock_chunk:
        mock_chunk.return_value = "Sample board posts"
        prompt, info_text, chunk, is_blat, is_warhammer = await _get_summarize_prompt_and_chunk(
            board_id="b", thread_id=None, thread_info={}, lang="ru", paragraph_count=3, is_blat=False, is_warhammer=False
        )
        assert prompt is not None
        assert len(prompt) > 0
        assert "За последние 6 часов на доске /b/" in info_text
        assert chunk == "Sample board posts"
        assert is_blat is False
        assert is_warhammer is False
