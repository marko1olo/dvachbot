import sys
lines = [182,504,505,839,2081,2161,3145,6232,8080,8445,8972,8984,12388,13738,14540,17368]
with open('main.py', encoding='utf8') as f:
    c = f.readlines()
with open('lines.txt', 'w', encoding='utf8') as out:
    for l in lines:
        out.write(f"{l}: {c[l-1].strip()}\n")
