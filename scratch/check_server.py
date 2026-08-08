import urllib.request
import urllib.error
import sys

def check_url(url):
    print(f"Checking {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"Response from {url}: {response.status} {response.reason}")
            return True, response.status
    except urllib.error.HTTPError as e:
        print(f"HTTPError from {url}: {e.code} {e.reason}")
        return True, e.code
    except Exception as e:
        print(f"Failed to connect to {url}: {e}")
        return False, None

if __name__ == "__main__":
    ok1, status1 = check_url("http://127.0.0.1:8000/")
    ok2, status2 = check_url("http://127.0.0.1:8000/b/")
    if ok1 or ok2:
        print("SERVER_IS_RUNNING")
        sys.exit(0)
    else:
        print("SERVER_IS_NOT_RUNNING")
        sys.exit(1)
