import sys
import os

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    path = r'C:\Users\danat\Documents\ввв.txt'
    if not os.path.exists(path):
        print("Log not found.")
        return
        
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print("Sample lines with 0 successes:")
    count = 0
    for idx, line in enumerate(lines):
        if "✅ 0/" in line:
            print(f"Line {idx}: {line.strip()}")
            count += 1
            if count >= 20:
                break
                
    # Let's count different phases
    phases = {}
    for line in lines:
        if "[" in line and "]" in line:
            phase = line.split("[")[1].split("]")[0]
            phases[phase] = phases.get(phase, 0) + 1
    print(f"\nPhases count: {phases}")

if __name__ == '__main__':
    main()
