import os
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    path = r'C:\Users\danat\Documents\ввв.txt'
    if not os.path.exists(path):
        print("Log not found.")
        return
        
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    print(f"Total log lines: {len(lines)}")
    
    # Let's find where the zero successes started, and how many there were in a row
    first_zero_idx = None
    consecutive_zeros = 0
    max_consecutive_zeros = 0
    zero_runs = []
    
    for idx, line in enumerate(lines):
        if "✅ 0/" in line:
            if first_zero_idx is None:
                first_zero_idx = idx
            consecutive_zeros += 1
        else:
            if consecutive_zeros > 0:
                zero_runs.append((first_zero_idx, idx - 1, consecutive_zeros))
                if consecutive_zeros > max_consecutive_zeros:
                    max_consecutive_zeros = consecutive_zeros
                first_zero_idx = None
                consecutive_zeros = 0
                
    if consecutive_zeros > 0:
        zero_runs.append((first_zero_idx, len(lines) - 1, consecutive_zeros))
        if consecutive_zeros > max_consecutive_zeros:
            max_consecutive_zeros = consecutive_zeros
            
    print(f"Number of zero success runs: {len(zero_runs)}")
    print(f"Max consecutive zero successes: {max_consecutive_zeros}")
    
    if zero_runs:
        print("\nAll zero success runs (start_line, end_line, length):")
        for run in zero_runs[:10]:
            # Get post numbers for start and end of run
            start_line = lines[run[0]]
            end_line = lines[run[1]]
            print(f"  Lines {run[0]}-{run[1]} (length {run[2]}):")
            print(f"    Start: {start_line.strip()}")
            print(f"    End:   {end_line.strip()}")
            
if __name__ == '__main__':
    main()
