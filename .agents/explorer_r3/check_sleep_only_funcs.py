with open(r"C:\Users\danat\Desktop\dvachbot\common\database.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

def get_func_text(func_name):
    out = []
    recording = False
    for idx, line in enumerate(lines, 1):
        if f"def {func_name}(" in line:
            recording = True
        elif recording and line.startswith("async def ") or (line.startswith("def ") and not line.startswith(f"def {func_name}")):
            break
        if recording:
            out.append(f"{idx:4d}: {line}")
    return "".join(out)

with open(r"C:\Users\danat\Desktop\dvachbot\.agents\explorer_r3\sleep_funcs.txt", "w", encoding="utf-8") as out:
    out.write(get_func_text("register_file_owners_batch"))
    out.write("\n\n" + "="*50 + "\n\n")
    out.write(get_func_text("postcopies_daily_cleanup_loop"))

print("Written to sleep_funcs.txt")
