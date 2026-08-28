import json
log_file = r'C:\Users\danat\.gemini\antigravity\brain\82f2f388-caea-40cb-8d4d-5262433981c5\.system_generated\logs\transcript_full.jsonl'
user_code = ''
admin_code = ''
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if 'write_to_file' in line or 'replace_file_content' in line or 'extract_phase6.py' in line:
            try:
                data = json.loads(line)
                for tc in data.get('tool_calls', []):
                    args = tc.get('arguments', {})
                    if 'TargetFile' in args:
                        if 'user_manager.py' in args['TargetFile'] and 'CodeContent' in args:
                            user_code = args['CodeContent']
                        if 'admin_manager.py' in args['TargetFile'] and 'CodeContent' in args:
                            admin_code = args['CodeContent']
            except Exception:
                import traceback; traceback.print_exc()

if user_code:
    with open('user_manager.py', 'w', encoding='utf-8') as f:
        f.write(user_code)
if admin_code:
    with open('admin_manager.py', 'w', encoding='utf-8') as f:
        f.write(admin_code)
print('Recovered user_manager:', len(user_code), 'admin_manager:', len(admin_code))
