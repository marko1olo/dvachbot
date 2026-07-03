import sys
with open('network_test.py', 'r') as f:
    lines = f.readlines()
with open('network_test.py', 'w') as f:
    skip = False
    for line in lines:
        if line.startswith('<<<<<<<'):
            skip = True
        elif line.startswith('======='):
            skip = False
        elif line.startswith('>>>>>>>'):
            continue
        elif not skip:
            f.write(line)
