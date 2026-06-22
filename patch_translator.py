import re

with open('japanese_translator.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('from typing import Optional, List, Dict, Callable, Awaitable', 'from typing import Optional, List, Dict, Awaitable')

dead_lines = 'async def _get_proxy_usage_strategy() -> bool: return True\nasync def _update_proxy_state_on_failure(): pass\n'
content = content.replace(dead_lines, '')

with open('japanese_translator.py', 'w', encoding='utf-8') as f:
    f.write(content)
