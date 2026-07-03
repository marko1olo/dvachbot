import re

with open("Dubsite_tgach/importer.py", "r") as f:
    content = f.read()

content = content.replace("from common.config import BIND_IPV4", "")

with open("Dubsite_tgach/importer.py", "w") as f:
    f.write(content)

with open("site_tgach/importer.py", "r") as f:
    content = f.read()

content = content.replace("from common.config import BIND_IPV4", "")

with open("site_tgach/importer.py", "w") as f:
    f.write(content)
