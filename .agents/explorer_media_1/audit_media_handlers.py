import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = r"C:\Users\danat\Desktop\dvachbot\site_tgach\main.py"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

lines = content.splitlines()

def print_section(start_line, end_line, title):
    print(f"\n==================== {title} (Lines {start_line}-{end_line}) ====================")
    for idx in range(start_line - 1, min(end_line, len(lines))):
        print(f"{idx+1:5d}: {lines[idx]}")

print_section(5610, 5650, "Random Img and Next Img Endpoints")
print_section(8740, 8780, "Roulette / TV Endpoints")
print_section(5545, 5600, "Media Feed Endpoint")
print_section(9130, 9170, "Voice Transcribe Endpoint")

