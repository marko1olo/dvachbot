import os
import sys

sys.path.insert(0, r"C:\Users\danat\Desktop\dvachbot")

os.environ["PYTHONUTF8"] = "1"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from verification_scripts.media_loading_probe import probe_media_endpoints

if __name__ == "__main__":
    probe_media_endpoints()
