import asyncio
import json
import time
import re

STOP_WORDS = set(['a', 'the', 'and'])

def process_posts_sync(posts):
    text_corpus = ""
    for row in posts:
        try:
            content_dict = json.loads(row[0])
            text = ""
            if content_dict.get('type') == 'text':
                text = content_dict.get('text', '')
            elif content_dict.get('type') in ['photo', 'video', 'animation', 'document']:
                text = content_dict.get('caption', '')

            if text:
                # Remove HTML tags
                text = re.sub(r'<[^>]+>', ' ', text)
                # Remove URLs
                text = re.sub(r'http[s]?://\S+', ' ', text)
                text_corpus += text + " "
        except Exception:
            continue

    words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text_corpus.lower())
    filtered_words = [w for w in words if w not in STOP_WORDS]
    final_text = " ".join(filtered_words)
    return final_text

async def monitor_event_loop():
    start = time.time()
    await asyncio.sleep(0)
    end = time.time()
    return end - start

async def main():
    print("Generating dummy data...")
    num_posts = 100000
    posts = [(json.dumps({"type": "text", "text": f"This is some sample text {i} with a <tag> and https://example.com/link."}),) for i in range(num_posts)]

    print("Testing blocking sync call...")
    loop = asyncio.get_running_loop()

    start_time = time.time()
    task = asyncio.create_task(asyncio.sleep(0)) # just something on loop
    result_sync = process_posts_sync(posts)
    await task
    end_time = time.time()
    print(f"Time taken (sync): {end_time - start_time:.4f} seconds (Event loop was blocked)")

    print("Testing non-blocking async call (to_thread)...")

    start_time = time.time()
    # We run the process in to_thread and concurrently run the monitor to see if event loop is blocked
    task_monitor = asyncio.create_task(monitor_event_loop())
    result_async = await asyncio.to_thread(process_posts_sync, posts)
    monitor_delay = await task_monitor
    end_time = time.time()

    print(f"Time taken (async): {end_time - start_time:.4f} seconds")
    print(f"Event loop delay during async: {monitor_delay:.4f} seconds (Should be close to 0)")

if __name__ == '__main__':
    asyncio.run(main())
