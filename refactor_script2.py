import re

def main():
    with open('main.py', 'r') as f:
        content = f.read()

    new_content = content.replace('cooldown_msg = f"{part1}\\\\n\\\\n{part2}"', 'cooldown_msg = f"{part1}\\n\\n{part2}"')

    with open('main.py', 'w') as f:
        f.write(new_content)
    print("Replaced successfully!")

if __name__ == '__main__':
    main()
