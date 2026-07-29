from fastapi import Response
import time
from email.utils import formatdate
from common.db_pool import get_pool
from common.board_config import BOARD_CONFIG
import json
import re
from xml.sax.saxutils import escape as xml_escape

CLEAN_HTML_RE = re.compile(r'<[^<]+?>')


def _cdata_safe(text: str) -> str:
    """
    Обезвреживает последовательность ']]>' внутри CDATA.

    Пост с текстом ']]>' закрывал секцию CDATA раньше времени, и остаток текста
    начинал парситься как разметка: лента становилась невалидным XML, а ридер
    отбрасывает такую ленту ЦЕЛИКОМ, не один пост. Разрываем маркер на две
    секции CDATA — склеенный парсером текст остаётся тем же байт в байт.
    """
    return text.replace(']]>', ']]]]><![CDATA[>')


async def generate_rss(board_id: str, request):
    """Генерирует RSS 2.0 для конкретной доски."""
    if board_id not in BOARD_CONFIG:
        return Response(status_code=404)
        
    board_name = BOARD_CONFIG[board_id]['name']
    base_url = str(request.base_url).rstrip('/')
    
    xml = ['<?xml version="1.0" encoding="UTF-8" ?>']
    xml.append('<rss version="2.0">')
    xml.append('<channel>')
    # Экранирование обязательно везде, где в XML попадает не-константа: один
    # '&' или '<' в имени доски/URL делает ленту невалидной для любого ридера.
    xml.append(f'<title>ТГАЧ - {xml_escape(board_name)}</title>')
    xml.append(f'<link>{xml_escape(base_url)}/{xml_escape(board_id)}/</link>')
    xml.append(f'<description>Последние треды в разделе {xml_escape(board_name)}</description>')
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
                try:
                    content = json.loads(content_raw)
                    raw_text = content.get('text')
                    # 'text' приходит null'ом у медиа-тредов и числом у битых
                    # записей: срез по не-строке бросал TypeError, и пост молча
                    # выпадал из ленты вместо заголовка "Media Thread".
                    if not isinstance(raw_text, str):
                        raw_text = ''
                    text = raw_text[:100] or "Media Thread"
                    # Очистка от HTML для RSS
                    clean_text = CLEAN_HTML_RE.sub('', text)

                    link = f"{base_url}/{board_id}/res/{pid}.html"
                    # Текст поста — пользовательский ввод. Без экранирования
                    # любое '&' или незакрытое '<' ломало ВСЮ ленту, а не пост.
                    title = xml_escape(f'#{pid} {clean_text}')
                    safe_link = xml_escape(link)

                    xml.append('<item>')
                    xml.append(f'<title>{title}...</title>')
                    xml.append(f'<link>{safe_link}</link>')
                    xml.append(f'<description><![CDATA[{_cdata_safe(text)}]]></description>')
                    xml.append(f'<pubDate>{formatdate(ts)}</pubDate>')
                    xml.append(f'<guid>{safe_link}</guid>')
                    xml.append('</item>')
                except Exception as e:
                    # Битый JSON или timestamp в одном посте не должен рвать
                    # ленту, но и глухое 'pass' плохо: пост исчезал бесследно.
                    # Голый except ловил ещё и BaseException (CancelledError,
                    # KeyboardInterrupt) — этого здесь быть не должно.
                    print(f"RSS: пропущен пост {pid}: {e}")

    except Exception as e:
        print(f"RSS Error: {e}")
        
    xml.append('</channel>')
    xml.append('</rss>')
    
    return Response(content="\n".join(xml), media_type="application/xml")