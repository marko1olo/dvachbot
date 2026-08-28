import re
import os

path = r'C:\Users\danat\Desktop\dvachbot\common\database.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix random sort
content = content.replace(
'''                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        LEFT JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                        GROUP BY p.post_num
                    """''',
'''                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        INNER JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                    """'''
)

# Fix bump or new sort
content = content.replace(
'''                    if sort_by == "bump":
                        order_clause = f"ORDER BY {pin_clause} MIN(IFNULL(t.is_archived, 0)) ASC, MAX(IFNULL(t.last_updated_at, p.timestamp)) DESC, p.post_num DESC"
                    else:
                        order_clause = f"ORDER BY {pin_clause} p.timestamp DESC, p.post_num DESC"
                    
                    limit_params = [page_size, offset]
                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        LEFT JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                        GROUP BY p.post_num
                        {order_clause}
                        LIMIT ? OFFSET ?
                    """''',
'''                    if sort_by == "bump":
                        order_clause = f"ORDER BY {pin_clause} IFNULL(t.is_archived, 0) ASC, IFNULL(t.last_updated_at, p.timestamp) DESC, p.post_num DESC"
                    else:
                        order_clause = f"ORDER BY {pin_clause} p.timestamp DESC, p.post_num DESC"
                    
                    limit_params = [page_size, offset]
                    ids_query = f"""
                        SELECT p.post_num
                        FROM Posts p
                        INNER JOIN Threads t ON p.post_num = t.thread_num
                        {where_clause}
                        {order_clause}
                        LIMIT ? OFFSET ?
                    """'''
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Optimized get_op_posts_for_board in database.py')
