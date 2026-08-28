import time
f = open("logs/bot_stdout_utf8.log", "r", encoding="utf-8")
f.seek(0, 2)
start = time.time()
while time.time() - start < 300:
    line = f.readline()
    if not line:
        time.sleep(1)
        continue
    line_lower = line.lower()
    if any(x in line_lower for x in ["broadcast", "sent", "отправлен", "рассылка", "dispatch", "error in handle_message", "handled message"]):
        print(line)
        break
