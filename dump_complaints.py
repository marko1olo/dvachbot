import json

with open('c:/Users/danat/Desktop/dvachbot/found_posts.json', 'r', encoding='utf-8') as f:
    posts = json.load(f)

with open('c:/Users/danat/Desktop/dvachbot/all_complaints.txt', 'w', encoding='utf-8') as out:
    for p in posts:
        text = p['text'].replace('\n', ' ')
        if len(text) > 15:
            out.write(f"Post {p['post_num']} (Auth: {p['author_id']}): {text}\n")
