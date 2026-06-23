import requests

url = 'https://api.github.com/repos/marko1olo/dvachbot/pulls?state=open'
try:
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    prs = response.json()
    if not prs:
        print('No open pull requests found.')
    for pr in prs:
        print(f"#{pr['number']} - {pr['title']}")
        print(f"   URL: {pr['html_url']}")
        print(f"   User: {pr['user']['login']}")
        print(f"   Diff URL: {pr['diff_url']}")
        print(f"   Body: {pr['body'][:200] if pr['body'] else 'No body'}")
        print('-'*40)
except Exception as e:
    print('Error:', e)
