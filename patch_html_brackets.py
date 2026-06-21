import re

def fix_html_brackets(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # We want to replace unescaped `<` and `>` with `&lt;` and `&gt;` inside standard response strings 
    # that are typically usage instructions like `<ID>`, `<text>`, `<word>`, etc.
    # It's safer to just explicitly replace known bad patterns:
    # <id>, <ID>, <текст>, <text>, <word>, <amount>, <сумма>
    
    bad_tags = ["id", "ID", "текст", "text", "word", "amount", "сумма", "time", "время"]
    
    new_content = content
    for tag in bad_tags:
        new_content = new_content.replace(f"<{tag}>", f"&lt;{tag}&gt;")
        
    if new_content != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("Patched main.py successfully.")
    else:
        print("No changes made.")

fix_html_brackets("main.py")
