import asyncio
import time
import random

# Mock spawn_task
def spawn_task(coro):
    return asyncio.create_task(coro)

# Mock save_success
async def save_success(path, token, bot_id):
    return path, token, bot_id

file_id = "test_file_id"
tried_tokens = set()

# Mock fetch
async def _fetch_telegram_path(file_id, token):
    # Simulate network delay, some bots are very slow
    delay = random.uniform(0.1, 1.0)
    await asyncio.sleep(delay)

    # Only one token has the file
    if token == "token_40":
        return "success/path"
    return None


async def try_bot_batch_original(bot_tokens, batch_size: int = 4):
    candidates = []
    for bot_id, token in bot_tokens:
        if not token or token in tried_tokens:
            continue
        tried_tokens.add(token)
        candidates.append((bot_id, token))

    async def fetch_with_bot(bot_id, token):
        path = await _fetch_telegram_path(file_id, token)
        if not path:
            return None
        return path, token, bot_id

    for start in range(0, len(candidates), batch_size):
        tasks = [
            spawn_task(fetch_with_bot(bot_id, token))
            for bot_id, token in candidates[start:start + batch_size]
        ]
        try:
            for task in asyncio.as_completed(tasks):
                result = await task
                if result:
                    for pending in tasks:
                        if not pending.done():
                            pending.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    return await save_success(*result)
        finally:
            pending_tasks = [task for task in tasks if not task.done()]
            for pending in pending_tasks:
                pending.cancel()
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
    return None

async def try_bot_batch_optimized(bot_tokens, batch_size: int = 4):
    candidates = []
    for bot_id, token in bot_tokens:
        if not token or token in tried_tokens:
            continue
        tried_tokens.add(token)
        candidates.append((bot_id, token))

    async def fetch_with_bot(bot_id, token):
        path = await _fetch_telegram_path(file_id, token)
        if not path:
            return None
        return path, token, bot_id

    pending = set()
    candidate_iter = iter(candidates)

    for _ in range(batch_size):
        try:
            bot_id, token = next(candidate_iter)
            pending.add(spawn_task(fetch_with_bot(bot_id, token)))
        except StopIteration:
            break

    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                # To maintain safety, consume exception if any (or it raises here)
                try:
                    result = await task
                except Exception:
                    result = None

                if result:
                    return await save_success(*result)

                try:
                    bot_id, token = next(candidate_iter)
                    pending.add(spawn_task(fetch_with_bot(bot_id, token)))
                except StopIteration:
                    pass
    finally:
        for task in pending:
            if not task.done():
                task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    return None


async def main():
    random.seed(42)
    # create 100 mock tokens
    tokens = [(i, f"token_{i}") for i in range(100)]

    print("Benchmarking original implementation...")
    start_time = time.time()
    global tried_tokens
    tried_tokens = set()
    res = await try_bot_batch_original(tokens)
    duration_original = time.time() - start_time
    print(f"Original took {duration_original:.2f} seconds, result: {res}")

    random.seed(42)
    print("\nBenchmarking optimized implementation...")
    start_time = time.time()
    tried_tokens = set()
    res = await try_bot_batch_optimized(tokens)
    duration_optimized = time.time() - start_time
    print(f"Optimized took {duration_optimized:.2f} seconds, result: {res}")

    print(f"\nSpeedup: {duration_original / duration_optimized:.2f}x")

if __name__ == "__main__":
    asyncio.run(main())
