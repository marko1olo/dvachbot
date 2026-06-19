def main():
    with open('main.py', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            if "['users']" in line or "users']" in line:
                if 'active' in line:
                    print(f"{i}: {line.strip()}")

if __name__ == '__main__':
    main()
