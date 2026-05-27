from fastapi import Response
import time
from email.utils import formatdate
from common.db_pool import get_pool
from common.board_config import BOARD_CONFIG

async def generate_rss(board_id: str, request):
    """Генерирует RSS 2.0 для конкретной доски."""
    if board_id not in BOARD_CONFIG:
        return Response(status_code=404)
        
    board_name = BOARD_CONFIG[board_id]['name']
    base_url = str(request.base_url).rstrip('/')
    
    xml = ['<?xml version="1.0" encoding="UTF-8" ?>']
    xml.append('<rss version="2.0">')
    xml.append('<channel>')
    xml.append(f'<title>ТГАЧ - {board_name}</title>')
    xml.append(f'<link>{base_url}/{board_id}/</link>')
    xml.append(f'<description>Последние треды в разделе {board_name}</description>')
    xml.append(f'<lastBuildDate>{formatdate(time.time())}</lastBuildDate>')
    
    db = await get_pool()
    try:
        # Берем последние 20 тредов
        query = """
            SELECT p.post_num, p.content, p.timestamp 
            FROM Posts p
            JOIN Threads t ON CAST(p.post_num AS TEXT) = t.thread_id
            WHERE p.board_id = ? 
            ORDER BY p.timestamp DESC LIMIT 20
        """
        async with db.execute(query, (board_id,)) as cursor:
            async for row in cursor:
                pid, content_raw, ts = row
                import json
                try:
                    content = json.loads(content_raw)
                    text = content.get('text', '')[:100] or "Media Thread"
                    # Очистка от HTML для RSS
                    import re
                    clean_text = re.sub('<[^<]+?>', '', text)
                    
                    link = f"{base_url}/{board_id}/res/{pid}.html"
                    
                    xml.append('<item>')
                    xml.append(f'<title>#{pid} {clean_text}...</title>')
                    xml.append(f'<link>{link}</link>')
                    xml.append(f'<description><![CDATA[{text}]]></description>')
                    xml.append(f'<pubDate>{formatdate(ts)}</pubDate>')
                    xml.append(f'<guid>{link}</guid>')
                    xml.append('</item>')
                except: pass
                
    except Exception as e:
        print(f"RSS Error: {e}")
        
    xml.append('</channel>')
    xml.append('</rss>')
    
    return Response(content="\n".join(xml), media_type="application/xml")