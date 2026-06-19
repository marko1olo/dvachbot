def main():
    with open('main.py', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            if "users']['active']" in line or "users']" in line:
                if 'select' in line.lower() or 'execute' in line.lower() or 'query' in line.lower() or 'get_' in line.lower() or 'load_' in line.lower():
                    print(f"{i}: {line.strip()}")
            if 'async def load_' in line or 'async def init_' in line:
                print(f"{i}: {line.strip()}")

if __name__ == '__main__':
    main()
