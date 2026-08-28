import os
with open('C:/Users/danat/Desktop/dvachbot/site_tgach/main.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        low = line.lower()
        if '???' in low or '????' in low:
            if '?????' in low or '???????' in low: continue
            print(f'Line {i+1}: {line.strip().encode("unicode_escape").decode("ascii")}')
