import sys
with open('site_tgach/importer.py', 'r', encoding='utf-8') as f:
    c = f.read()
c = c.replace('async with get_db_connection() as conn:\
                async with db_lock:', 'async with db_lock, get_db_connection() as conn:')
with open('site_tgach/importer.py', 'w', encoding='utf-8') as f:
    f.write(c)
