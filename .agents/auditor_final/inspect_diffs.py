import subprocess
import os

modified_files = [
    'user_manager.py',
    'periodic_publisher.py',
    'broadcaster.py',
    'delivery_manager.py',
    'post_processor.py',
    'economy_extension.py',
    'admin_manager.py',
    'handlers/message_router.py',
    'site_tgach/importer.py',
    'site_tgach/mirror_worker.py',
    'site_tgach/main.py',
    'Dubsite_tgach/main.py',
    'main.py',
    'archive_manager.py',
    'bot_helpers.py',
    'media_utils.py',
    'post_helpers.py'
]

diff_dir = r"C:\Users\danat\Desktop\dvachbot\.agents\auditor_final\diffs"
os.makedirs(diff_dir, exist_ok=True)

for fname in modified_files:
    cmd = ['git', 'diff', '--', fname]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    diff_text = res.stdout
    out_path = os.path.join(diff_dir, fname.replace('/', '_') + '.diff')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(diff_text)
    print(f"{fname}: {len(diff_text)} bytes diff")
