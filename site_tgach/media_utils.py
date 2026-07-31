def detect_media_type(data: bytes, url: str) -> str:
    """
    Определяет тип медиа (photo/video/animation) по заголовку файла или URL.
    """
    header = data[:12]
    url_lower = url.lower()
    if b'ftyp' in header or header.startswith(b'\x1A\x45\xDF\xA3'):
        return 'video'
    if header.startswith(b'GIF8'):
        return 'animation'
    if url_lower.endswith('.mp4') or url_lower.endswith('.webm') or url_lower.endswith('.mov'):
        return 'video'
    if url_lower.endswith('.gif'):
        return 'animation'
    return 'photo'
