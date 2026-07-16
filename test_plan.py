import re
with open("common/database.py", "r") as f:
    code = f.read()

print("fetchall:", len(re.findall(r"fetchall\(\)", code[130648:136618])))
print("fetchone:", len(re.findall(r"fetchone\(\)", code[130648:136618])))
print("total_changes:", len(re.findall(r"total_changes", code[130648:136618])))
