import os
import glob

def main():
    root = r"C:\Users\danat\Desktop\dvachbot"
    skip_dirs = {'.git', '.venv', '.mypy_cache', '.pytest_cache', '__pycache__'}
    
    files_with_time = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for f in filenames:
            full_path = os.path.join(dirpath, f)
            try:
                mtime = os.path.getmtime(full_path)
                files_with_time.append((mtime, full_path))
            except Exception:
                pass
                
    files_with_time.sort(key=lambda x: x[0], reverse=True)
    
    top5 = files_with_time[:5]
    print("TOP 5 MODIFIED FILES:")
    for mtime, filepath in top5:
        print(f"\n--- {filepath} ---")
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as fp:
                lines = [fp.readline() for _ in range(30)]
                print(''.join([l for l in lines if l]))
        except Exception as e:
            print(f"Error reading file: {e}")

if __name__ == "__main__":
    main()
