import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

test_files = [
    'tests/test_html_anchors.py',
    'tests/test_media_resiliency.py',
    'tests/test_files_endpoint.py',
    'tests/test_e2e_unified_suite.py',
    'tests/test_html_anchors_frontend.js',
    'tests/test_frontend_fallback.js',
    'tests/test_e2e_unified_suite_fe.js'
]

for tf in test_files:
    exists = os.path.exists(tf)
    size = os.path.getsize(tf) if exists else 0
    print(f'{tf}: Exists={exists}, Size={size} bytes')
