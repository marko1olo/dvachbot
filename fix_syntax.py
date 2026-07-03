with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the broken lines
broken = 'print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")'
fixed = 'print(f"Критическая ошибка в delete_user_posts: {e}\\n{traceback.format_exc()}")'

content = content.replace(broken, fixed)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)
