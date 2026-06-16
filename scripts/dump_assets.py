import sys
import os
import json
import re
import types
sys.path.append('.')
import text_assets

assets = {}
for k, v in vars(text_assets).items():
    if k.startswith('__'):
        continue
    if isinstance(v, (types.ModuleType, type, types.FunctionType, types.BuiltinFunctionType)):
        continue
    
    # We must handle compiled regex patterns if they exist
    def sanitize(obj):
        if isinstance(obj, dict):
            new_dict = {}
            for dk, dv in obj.items():
                if isinstance(dk, re.Pattern):
                    new_dict[dk.pattern] = sanitize(dv)
                else:
                    new_dict[str(dk)] = sanitize(dv)
            return new_dict
        elif isinstance(obj, list):
            return [sanitize(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(sanitize(item) for item in obj)
        elif isinstance(obj, re.Pattern):
            return obj.pattern
        else:
            return obj

    try:
        sanitized = sanitize(v)
        # Attempt to json dumps to verify it's serializable
        json.dumps(sanitized)
        assets[k] = sanitized
    except Exception as e:
        print(f"Skipping {k} due to {e}")

os.makedirs('data', exist_ok=True)
with open('data/text_assets.json', 'w', encoding='utf-8') as f:
    json.dump(assets, f, ensure_ascii=False, indent=2)

print(f"Successfully exported {len(assets)} keys to data/text_assets.json")
