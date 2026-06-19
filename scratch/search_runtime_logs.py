import os
import json
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    log_dir = 'logs'
    
    # We will search for delivery_result in logs and print their interrupted_reason
    reasons = {}
    found_samples = []
    
    for file in os.listdir(log_dir):
        if file.startswith('bot_runtime.log') or file == 'bot_stdout_utf8.log':
            path = os.path.join(log_dir, file)
            print(f"Searching in {path}...")
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if 'delivery_result' in line:
                            # Try to extract JSON
                            try:
                                # Find JSON part in line
                                # Typically: INFO: ...: delivery_result {"ts":...}
                                json_idx = line.find('{"')
                                if json_idx != -1:
                                    data = json.loads(line[json_idx:])
                                    reason = data.get('interrupted_reason')
                                    if reason:
                                        reasons[reason] = reasons.get(reason, 0) + 1
                                        if len(found_samples) < 15:
                                            found_samples.append((file, data))
                            except Exception as e:
                                pass
            except Exception as e:
                print(f"Error reading {file}: {e}")
                
    print(f"\nAll interrupted reasons found: {reasons}")
    print("\nSamples:")
    for file, sample in found_samples:
        print(f"  [{file}]: Board {sample.get('board_id')}, Post {sample.get('post_num')}, Phase {sample.get('phase')}, Success: {sample.get('success')}/{sample.get('phase_recipients')}, Def: {sample.get('deferred_recipients')}, Limit_Def: {sample.get('budget_deferred')}, Reason: {sample.get('interrupted_reason')}, Time: {sample.get('seconds')}s")

if __name__ == '__main__':
    main()
