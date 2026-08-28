import re

path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix read_board_index_redirect
old1 = '''@app.get("/{board_id}/")
async def read_board_index_redirect(board_id: str):'''

new1 = '''@app.get("/{board_id}/")
async def read_board_index_redirect(board_id: str):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404)'''

if old1 in content and new1 not in content:
    content = content.replace(old1, new1)

# Fix read_res_root_redirect
old2 = '''@app.get("/{board_id}/res/")
async def read_res_root_redirect(board_id: str):'''

new2 = '''@app.get("/{board_id}/res/")
async def read_res_root_redirect(board_id: str):
    if board_id not in BOARD_CONFIG:
        raise HTTPException(status_code=404)'''

if old2 in content and new2 not in content:
    content = content.replace(old2, new2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed fastAPI catch-all route redirects in main.py')
