import re

with open("common/database.py", "r") as f:
    code = f.read()

# Just verifying we can find the right block
start = code.find("def _delete_in_chunks")
end = code.find("def cleanup_old_posts_from_db")
print("Functions to refactor found between characters:", start, "and", end)
