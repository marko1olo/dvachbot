import asyncio
import json
import time
import re

# Mock STOP_WORDS
STOP_WORDS = set(['a', 'the', 'and'])

def get_text_corpus_sync(posts):
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

async def main():
    # create dummy data
    print("Generating dummy data...")
    num_posts = 100000
    posts = []
    for i in range(num_posts):
        doc = {"type": "text", "text": f"This is some sample text {i} with a <tag> and https://example.com/link."}
        posts.append((json.dumps(doc),))

    print("Running baseline...")
    start_time = time.time()

    # Run sync version
    result_sync = get_text_corpus_sync(posts)

    end_time = time.time()
    print(f"Time taken (sync): {end_time - start_time:.4f} seconds")

    print("Running optimized...")
    start_time = time.time()

    # Run async version using to_thread
    result_async = await asyncio.to_thread(get_text_corpus_sync, posts)

    end_time = time.time()
    print(f"Time taken (async): {end_time - start_time:.4f} seconds")

    assert result_sync == result_async

if __name__ == '__main__':
    asyncio.run(main())
