with open("tests/test_main.py", "r") as f:
    content = f.read()
if "from Dubsite_tgach.main import vibe_to_icon" not in content:
    content = content.replace("from Dubsite_tgach.main import clean_title_text", "from Dubsite_tgach.main import clean_title_text, vibe_to_icon")
    with open("tests/test_main.py", "w") as f:
        f.write(content)
