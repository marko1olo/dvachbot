import ast
import sys

source_file = r'C:/Users/danat/Desktop/dvachbot/main.py'
target_file = r'C:/Users/danat/Desktop/dvachbot/post_helpers.py'

with open(source_file, 'r', encoding='utf-8') as f:
    source_lines = f.readlines()
    source_code = ''.join(source_lines)

tree = ast.parse(source_code)
functions_to_extract = {
    'format_header',
    'format_thread_post_header',
    'apply_shadow_autoreplace',
    'check_post_numerals',
    'execute_auto_roast'
}

extracted_code = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in functions_to_extract:
        start = node.lineno - 1
        end = node.end_lineno
        extracted_code.append(''.join(source_lines[start:end]))

imports = '''import asyncio
from shared_state import *
try:
    from moderation_config import *
except ImportError:
    import traceback; traceback.print_exc()
from broadcaster import MessageBroadcaster, DeliveryResults, _trim_post_copy_maps_unlocked, _order_recipients_for_delivery, _build_lie_media_content, _format_message_body, add_you_to_my_posts_fast
from utils import split_text
import itertools
from common.task_manager import spawn_task
import faulthandler
import gc
import psutil
try:
    import ujson as json
except ImportError:
    import json
import logging
import os
import shutil
import tempfile
import tracemalloc
import uuid
import math
import random
import re
import secrets
import html
import signal
'''

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(imports + '\n' + '\n'.join(extracted_code))

print('Extraction complete.')
