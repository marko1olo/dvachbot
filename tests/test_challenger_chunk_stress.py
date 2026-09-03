# -*- coding: utf-8 -*-
"""
test_challenger_chunk_stress.py
Adversarial Empirical Stress Testing Suite for get_board_chunk and _format_post_text.
"""

import time
import pytest
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import main
import ai_manager
import post_helpers
from post_helpers import _format_post_text, _format_media_context, _MEDIA_DESC_CACHE

UTC = timezone.utc


class TestChallengerChunkStress(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orig_messages = main.messages_storage.copy()
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

    async def asyncTearDown(self):
        main.messages_storage.clear()
        main.messages_storage.update(self.orig_messages)
        _MEDIA_DESC_CACHE.clear()

    # =========================================================================
    # TEST SUITE 1: HIGH PAYLOAD CHUNK COMPILATION (0, 50, 100, 200 PHOTOS)
    # =========================================================================

    async def _populate_payload(self, total_posts: int, photo_count: int, desc_prefix: str = "desc"):
        """Populates main.messages_storage with total_posts, containing photo_count photos."""
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

        step = max(1, total_posts // photo_count) if photo_count > 0 else total_posts + 1
        photos_placed = 0

        for i in range(1, total_posts + 1):
            is_photo = (photos_placed < photo_count) and (photo_count == total_posts or (i % step == 0))
            if is_photo:
                photos_placed += 1
                fid = f"payload_fid_{desc_prefix}_{i}"
                _MEDIA_DESC_CACHE[fid] = {
                    'description': f'High resolution image #{i} of landscape',
                    'tags': f'tag_{i}, scenery, photo_{i}'
                }
                content = {
                    'type': 'photo',
                    'file_id': fid,
                    'text': f'Photo caption #{i}' if i % 2 == 0 else ''
                }
            else:
                content = {
                    'type': 'text',
                    'text': f'Regular text discussion message #{i} with typical length and words.'
                }

            main.messages_storage[i] = {
                'author_id': 1000 + (i % 25),
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': content
            }

    async def test_high_payload_0_photos(self):
        """Verify 200 posts with 0 photos."""
        await self._populate_payload(200, 0, "0photo")
        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) > 0
        assert "[Фото:" not in chunk
        assert "[photo]" not in chunk

    async def test_high_payload_50_photos(self):
        """Verify 200 posts with 50 photos."""
        await self._populate_payload(200, 50, "50photo")
        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) > 0
        assert chunk.count("[Фото:") == 50

    async def test_high_payload_100_photos(self):
        """Verify 200 posts with 100 photos."""
        await self._populate_payload(200, 100, "100photo")
        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) > 0
        assert chunk.count("[Фото:") == 100

    async def test_high_payload_200_photos(self):
        """Verify 200 posts with 200 photos."""
        await self._populate_payload(200, 200, "200photo")
        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) > 0
        assert chunk.count("[Фото:") == 200

    # =========================================================================
    # TEST SUITE 2: EXECUTION TIME PROFILING & BENCHMARKING
    # =========================================================================

    async def test_execution_time_profiling_matrix(self):
        """
        Profiles get_board_chunk over 100 iterations for 0, 50, 100, 200 photos.
        Records min, avg, median, 95th percentile, and max execution times.
        """
        scenarios = [0, 50, 100, 200]
        results = {}

        for photo_count in scenarios:
            await self._populate_payload(200, photo_count, f"matrix_{photo_count}")
            # Warm up
            for _ in range(5):
                _ = await main.get_board_chunk('b', hours=1)

            times = []
            iterations = 100
            for _ in range(iterations):
                t0 = time.perf_counter()
                _ = await main.get_board_chunk('b', hours=1)
                t1 = time.perf_counter()
                times.append((t1 - t0) * 1000)

            times.sort()
            avg_t = sum(times) / len(times)
            med_t = times[len(times) // 2]
            p95_t = times[int(len(times) * 0.95)]
            min_t = times[0]
            max_t = times[-1]

            results[photo_count] = {
                'min': min_t,
                'avg': avg_t,
                'median': med_t,
                'p95': p95_t,
                'max': max_t
            }
            print(f"\n[PROFILING] 200 posts / {photo_count:3d} photos -> avg: {avg_t:.4f}ms | median: {med_t:.4f}ms | p95: {p95_t:.4f}ms | min: {min_t:.4f}ms | max: {max_t:.4f}ms")

    async def test_detailed_substage_breakdown(self):
        """
        Adversarial micro-benchmarking: breaks down exact CPU time spent in each stage of chunk compilation.
        """
        await self._populate_payload(200, 50, "breakdown")
        
        # Breakdown steps for 200 posts
        # 1. Post filtering and sorting
        t0 = time.perf_counter()
        for _ in range(100):
            board_posts = []
            for p in main.messages_storage.values():
                if p.get('board_id') == 'b' and p.get('author_id') != 0:
                    board_posts.append((main.normalize_storage_timestamp(p.get('timestamp')), p))
            board_posts.sort(key=lambda x: x[0])
            target_posts = board_posts[-200:]
        t_sort = ((time.perf_counter() - t0) / 100) * 1000

        # 2. Extract file_ids
        t0 = time.perf_counter()
        for _ in range(100):
            file_ids = set()
            for post in target_posts:
                c = post[1].get('content', {})
                if isinstance(c, dict):
                    fid = c.get('file_id')
                    if fid and isinstance(fid, str):
                        file_ids.add(fid)
                    for m in c.get('media', []):
                        if isinstance(m, dict) and m.get('file_id') and isinstance(m.get('file_id'), str):
                            file_ids.add(m.get('file_id'))
        t_fids = ((time.perf_counter() - t0) / 100) * 1000

        # 3. Formatting loop
        t0 = time.perf_counter()
        for _ in range(100):
            lines = []
            for _, post in target_posts:
                content = post.get('content', {})
                msg_type = content.get('type', 'text')
                fid = content.get('file_id')
                media_meta = _MEDIA_DESC_CACHE.get(fid) if fid else None
                text = _format_post_text(content, msg_type, media_meta=media_meta)
                if text:
                    name = main._get_author_name(post, content, 'b', None)
                    reply_suffix = main._get_reply_suffix(post, content, 'b', None)
                    lines.append(f"{name}{reply_suffix}: {text}")
        t_format = ((time.perf_counter() - t0) / 100) * 1000

        # 4. Reverse accumulation & newline cleanup
        t0 = time.perf_counter()
        for _ in range(100):
            total_len = 0
            limited_lines = []
            for line in reversed(lines):
                line_clean = line.strip()
                if not line_clean:
                    continue
                if '\n\n' in line_clean:
                    import re
                    line_clean = re.sub(r'\n{2,}', '\n', line_clean)
                line_len = len(line_clean)
                if total_len + line_len + 1 > 35000:
                    break
                limited_lines.append(line_clean)
                total_len += line_len + 1
            limited_lines.reverse()
            cleaned_chunk = "\n".join(limited_lines)
        t_accum = ((time.perf_counter() - t0) / 100) * 1000

        print(f"\n[BREAKDOWN] 200 posts micro-timing:")
        print(f"  1. Storage scan & sort (200 posts): {t_sort:.4f} ms")
        print(f"  2. File_id extraction (200 posts):   {t_fids:.4f} ms")
        print(f"  3. Formatting & Anon naming (200p):  {t_format:.4f} ms")
        print(f"  4. 35k Reverse accumulation (200p):  {t_accum:.4f} ms")
        print(f"  Total summed:                        {(t_sort + t_fids + t_format + t_accum):.4f} ms")

    # =========================================================================
    # TEST SUITE 3: SINGLE BATCHED QUERY EXECUTION AUDIT (NO N+1)
    # =========================================================================

    async def test_single_batched_query_uncached_media(self):
        """
        Verify exactly 1 DB query when 50 posts have uncached media file_ids.
        Confirm no individual (N+1) queries occur.
        """
        _MEDIA_DESC_CACHE.clear()
        main.messages_storage.clear()

        # 50 photo posts with uncached file_ids
        for i in range(1, 51):
            main.messages_storage[i] = {
                'author_id': 1000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'photo',
                    'file_id': f'uncached_fid_{i}',
                    'text': f'Uncached post #{i}'
                }
            }

        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            (f'uncached_fid_{i}', f'tag_{i}', f'Description {i}')
            for i in range(1, 51)
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_cursor
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_ctx

        with patch('common.database.get_pool', return_value=mock_db):
            chunk = await main.get_board_chunk('b', hours=1)

        # Ensure EXACTLY 1 query was executed
        assert mock_db.execute.call_count == 1, f"Expected 1 batch query, got {mock_db.execute.call_count}"
        query_sql, params = mock_db.execute.call_args[0]
        assert "WHERE file_id IN (" in query_sql
        assert len(params) == 50

        # Verify second call executes 0 queries due to cache
        with patch('common.database.get_pool', return_value=mock_db):
            chunk2 = await main.get_board_chunk('b', hours=1)
        assert mock_db.execute.call_count == 1  # count unchanged!

    async def test_single_batched_query_with_duplicate_file_ids(self):
        """
        Verify that multiple posts referencing the SAME file_id are deduplicated
        in the single batched query.
        """
        _MEDIA_DESC_CACHE.clear()
        main.messages_storage.clear()

        # 20 posts referencing only 2 distinct file_ids
        for i in range(1, 21):
            fid = "shared_fid_A" if i % 2 == 0 else "shared_fid_B"
            main.messages_storage[i] = {
                'author_id': 1000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'photo',
                    'file_id': fid,
                    'text': f'Post #{i}'
                }
            }

        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            ('shared_fid_A', 'tag_a', 'Desc A'),
            ('shared_fid_B', 'tag_b', 'Desc B')
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_cursor
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_ctx

        with patch('common.database.get_pool', return_value=mock_db):
            chunk = await main.get_board_chunk('b', hours=1)

        assert mock_db.execute.call_count == 1
        query_sql, params = mock_db.execute.call_args[0]
        # Query parameters should have exactly 2 deduplicated IDs
        assert len(params) == 2
        assert set(params) == {'shared_fid_A', 'shared_fid_B'}

    async def test_single_batched_query_with_media_groups_and_nested_attachments(self):
        """
        Verify that posts with content['media'] list are extracted and batched in 1 query.
        """
        _MEDIA_DESC_CACHE.clear()
        main.messages_storage.clear()

        main.messages_storage[1] = {
            'author_id': 1001,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'media_group',
                'media': [
                    {'type': 'photo', 'file_id': 'nested_fid_1'},
                    {'type': 'photo', 'file_id': 'nested_fid_2'}
                ],
                'text': 'Media album'
            }
        }

        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [
            ('nested_fid_1', 'tag_1', 'Album pic 1'),
            ('nested_fid_2', 'tag_2', 'Album pic 2')
        ]
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_cursor
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_ctx

        with patch('common.database.get_pool', return_value=mock_db):
            chunk = await main.get_board_chunk('b', hours=1)

        assert mock_db.execute.call_count == 1
        query_sql, params = mock_db.execute.call_args[0]
        assert set(params) == {'nested_fid_1', 'nested_fid_2'}

    async def test_single_batched_query_negative_caching_on_db_miss(self):
        """
        Verify negative caching: when DB returns no row for a file_id,
        it is cached as empty, preventing subsequent queries on future calls.
        """
        _MEDIA_DESC_CACHE.clear()
        main.messages_storage.clear()

        # Case 1: Photo only without text -> falls back to [photo]
        main.messages_storage[1] = {
            'author_id': 1001,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'non_existent_fid_404'
            }
        }
        # Case 2: Photo with caption -> falls back to caption text
        main.messages_storage[2] = {
            'author_id': 1002,
            'timestamp': datetime.now(UTC),
            'board_id': 'b',
            'content': {
                'type': 'photo',
                'file_id': 'non_existent_fid_405',
                'caption': 'Ghost caption'
            }
        }

        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = []  # DB returns nothing
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_cursor
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_ctx

        with patch('common.database.get_pool', return_value=mock_db):
            chunk1 = await main.get_board_chunk('b', hours=1)

        assert mock_db.execute.call_count == 1
        assert "[photo]" in chunk1
        assert "Ghost caption" in chunk1

        # Second call: verify no DB query is triggered
        with patch('common.database.get_pool', return_value=mock_db):
            chunk2 = await main.get_board_chunk('b', hours=1)
        assert mock_db.execute.call_count == 1  # still 1, no N+1 query loop!

    # =========================================================================
    # TEST SUITE 4: EXTREME BOUNDARY TEST (35,000 CHARACTERS BUDGET)
    # =========================================================================

    async def test_boundary_35000_massive_descriptions_and_tags(self):
        """
        Stress-test 35,000 character limit when descriptions and tags are massive (5,000 chars each).
        Verify truncation in _format_media_context prevents bloat and output strictly <= 35,000.
        """
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

        for i in range(1, 100):
            fid = f"huge_fid_{i}"
            _MEDIA_DESC_CACHE[fid] = {
                'description': f"Massive Description {i} " + ("А" * 5000),
                'tags': ", ".join([f"tag_{j}" for j in range(1000)])
            }
            main.messages_storage[i] = {
                'author_id': 2000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'photo',
                    'file_id': fid,
                    'text': f"Post text {i} " + ("Б" * 1000)
                }
            }

        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) <= 35000, f"Chunk exceeded 35,000 limit: {len(chunk)}"
        assert len(chunk) > 0
        # Check newest posts are present
        assert "Post text 99" in chunk

    async def test_boundary_exact_35000_char_budget(self):
        """
        Verify exact boundary conditions near 35,000 characters without line clipping.
        """
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

        # Seed posts with exact sizes
        for i in range(1, 40):
            main.messages_storage[i] = {
                'author_id': 3000 + i,
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': {
                    'type': 'text',
                    'text': f"HEADER_{i:02d}: " + ("Z" * 980)  # ~1000 chars per post
                }
            }

        chunk = await main.get_board_chunk('b', hours=1)
        assert len(chunk) <= 35000
        lines = chunk.split('\n')
        # All lines should be intact (no truncated mid-sentence / mid-line cuts)
        for line in lines:
            assert line.startswith("Анон [") or line.startswith("Anon [") or line.startswith("HEADER_")
            assert len(line) > 0

    async def test_boundary_adversarial_malformed_inputs(self):
        """
        Adversarial inputs: None values, integers, boolean types, nested dicts,
        empty strings, unicode emojis, control characters.
        """
        adversarial_cases = [
            None,
            {},
            {'description': None, 'tags': None},
            {'description': 12345, 'tags': [1, 2, 3]},
            {'description': True, 'tags': False},
            {'description': '   \n\t  ', 'tags': '   '},
            {'description': '\x00\x01\x02\x03', 'tags': 'test'},
            {'description': '🔥' * 500, 'tags': '🐱' * 200},
            {'description': '<script>alert(1)</script>', 'tags': '<b>tag</b>'},
            {'formatted': '[Фото: Manual Override]'}  # Pre-formatted cache injection
        ]

        for meta in adversarial_cases:
            res = _format_media_context(meta)
            # Must never raise exception
            if meta == {'formatted': '[Фото: Manual Override]'}:
                assert res == '[Фото: Manual Override]'
            elif isinstance(res, str):
                assert res.startswith('[Фото: ')
                assert res.endswith(']')
