# text_assets.py
import json
import os
import re

_current_dir = os.path.dirname(os.path.abspath(__file__))
_json_path = os.path.join(_current_dir, 'data', 'text_assets.json')

with open(_json_path, 'r', encoding='utf-8') as f:
    _data = json.load(f)

for key, value in _data.items():
    if key.startswith('CONTEXTUAL_REPLIES'):
        # Recompile regex patterns
        _data[key] = {re.compile(k, re.IGNORECASE): v for k, v in value.items()}

# Inject all text assets into the module namespace
globals().update(_data)
