import json
out = []
with open('c:/Users/danat/Desktop/dvachbot/main.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if ('audio' in line.lower() or 'voice' in line.lower() or 'flood' in line.lower() or 'burst' in line.lower()) and ('limit' in line.lower() or 'мут' in line.lower() or 'spam' in line.lower() or 'count' in line.lower()):
            out.append(f"{i+1}: {line.strip()}")
            
with open('c:/Users/danat/Desktop/dvachbot/main_audio_utf8.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
