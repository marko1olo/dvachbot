import sys
import os
import types
import re
from unittest.mock import MagicMock

# Read main.py directly to extract sanitize_html without running into circular/heavy imports
with open("main.py", "r") as f:
    code = f.read()

# We need the regexes
import_regexes = []
for line in code.split('\n'):
    if line.startswith("RE_SCRIPT_TAG") or line.startswith("RE_SCRIPT_SINGLE") or line.startswith("RE_DANGEROUS_TAGS") or line.startswith("RE_DANGEROUS_SINGLE") or line.startswith("RE_EVENT_HANDLERS"):
        import_regexes.append(line)

exec("\n".join(import_regexes))

# Extract sanitize_html function
sanitize_html_code = []
in_func = False
for line in code.split('\n'):
    if line.startswith("def sanitize_html"):
        in_func = True
        sanitize_html_code.append(line)
    elif in_func:
        if line.startswith("def ") and not line.startswith("    def link_replacer"):
            break
        sanitize_html_code.append(line)

exec("\n".join(sanitize_html_code))

print(sanitize_html('hello <a href="https://www.example.com">my link</a> world'))
print(sanitize_html('hello <a href="http://example.com">my link</a> world'))
print(sanitize_html('hello <a href="example.com">my link</a> world'))
print(sanitize_html('hello <a href="https://example.com/page?test=1">my link</a> world'))
print(sanitize_html('hello <a href="http://www.example.com/index.html">my link</a> world'))
