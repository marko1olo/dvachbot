import sys

with open('site_tgach/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.rfind('if __name__ == "__main__":')
if idx != -1:
    main_block = content[idx:]
    above_main = content[:idx]
    
    route_idx = main_block.find('@app.get("/api/is-ru")')
    if route_idx != -1:
        routes = main_block[route_idx:]
        new_main_block = main_block[:route_idx]
        
        new_content = above_main + routes + '\n\n' + new_main_block
        with open('site_tgach/main.py', 'w', encoding='utf-8') as fw:
            fw.write(new_content)
        print('Fixed routes position!')
    else:
        print('Routes not found in main block.')
else:
    print('__main__ block not found.')
