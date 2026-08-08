import filecmp
from pathlib import Path

f1 = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js")
f2 = Path(r"C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.js")

same = filecmp.cmp(f1, f2, shallow=False)
print(f"Byte-for-byte equality: {same}")
if not same:
    b1 = f1.read_bytes()
    b2 = f2.read_bytes()
    print(f"Sizes: main.src.js={len(b1)} bytes, main.js={len(b2)} bytes")
