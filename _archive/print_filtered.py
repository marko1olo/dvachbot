import json
with open('c:/Users/danat/Desktop/dvachbot/found_posts.json', 'r', encoding='utf-8') as f:
    posts = json.load(f)

with open('c:/Users/danat/Desktop/dvachbot/filtered_posts.txt', 'w', encoding='utf-8') as out:
    for p in posts:
        if len(p['text']) > 15:
            out.write(f"Post {p['post_num']} (Author {p['author_id']}): {p['text']}\n")
            out.write("-" * 40 + "\n")
