# -*- coding: utf-8 -*-
import time
import pytest
import unittest
from datetime import datetime, timezone
import main
from post_helpers import _MEDIA_DESC_CACHE

UTC = timezone.utc

class TestRichChunkBenchmark(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orig_messages = main.messages_storage.copy()
        main.messages_storage.clear()
        _MEDIA_DESC_CACHE.clear()

        # Seed 200 posts (50 photos + 150 text posts)
        for i in range(1, 201):
            if i % 4 == 0:
                fid = f"bench_photo_{i}"
                _MEDIA_DESC_CACHE[fid] = {
                    'description': f'Visual description of artifact {i} in high detail',
                    'tags': f'tag_{i}, anime, landscape, aesthetic'
                }
                content = {
                    'type': 'photo',
                    'file_id': fid,
                    'text': f'Photo caption for item {i}' if i % 8 == 0 else ''
                }
            else:
                content = {
                    'type': 'text',
                    'text': f'Message content {i} discussing board topic with multiple sentences.'
                }

            main.messages_storage[i] = {
                'author_id': 1000 + (i % 20),
                'timestamp': datetime.now(UTC),
                'board_id': 'b',
                'content': content
            }

    async def asyncTearDown(self):
        main.messages_storage.clear()
        main.messages_storage.update(self.orig_messages)
        _MEDIA_DESC_CACHE.clear()

    async def test_chunk_compilation_sub_millisecond_benchmark(self):
        # Warm-up run
        _ = await main.get_board_chunk('b', hours=1)

        # Benchmark 50 iterations
        iterations = 50
        start = time.perf_counter()
        for _ in range(iterations):
            chunk = await main.get_board_chunk('b', hours=1)
        elapsed_total = time.perf_counter() - start

        avg_ms = (elapsed_total / iterations) * 1000
        print(f"\n[BENCHMARK] get_board_chunk avg compilation time for 200 posts: {avg_ms:.4f} ms")

        # Sub-millisecond SLA assertion (< 1.0 ms per 200 posts)
        assert avg_ms < 1.0, f"Compilation SLA violation: {avg_ms:.4f} ms >= 1.0 ms"
        assert len(chunk) > 0
        assert "[Фото: " in chunk
