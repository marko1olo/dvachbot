import io
from PIL import Image

MAX_DIMENSION_SUM = 10000
MAX_ASPECT_RATIO = 20.0
MAX_FILE_SIZE_BYTES = 9.5 * 1024 * 1024


def _is_media_format(header: bytes) -> bool:
    """Check if the given header belongs to an unmodifiable media format (video/GIF)."""
    return (
        b'ftyp' in header or
        header.startswith(b'\x1A\x45\xDF\xA3') or
        header.startswith(b'GIF8')
    )


def _needs_resize_dims(width: int, height: int) -> bool:
    """Check if the dimensions exceed constraints."""
    return (
        (width + height > MAX_DIMENSION_SUM) or
        (width / height > MAX_ASPECT_RATIO) or
        (height / width > MAX_ASPECT_RATIO)
    )


def _calculate_new_dimensions(width: int, height: int) -> tuple[int, int]:
    """Calculate target dimensions maintaining constraints and aspect ratio."""
    new_width, new_height = width, height

    if width + height > MAX_DIMENSION_SUM:
        scale_factor = MAX_DIMENSION_SUM / (width + height)
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)

    if new_width / new_height > MAX_ASPECT_RATIO:
        new_width = int(new_height * MAX_ASPECT_RATIO)
    elif new_height / new_width > MAX_ASPECT_RATIO:
        new_height = int(new_width * MAX_ASPECT_RATIO)

    return max(1, new_width), max(1, new_height)


def _compress_and_save(img: Image.Image) -> bytes:
    """Compress image and reduce dimensions iteratively until it fits within MAX_FILE_SIZE_BYTES."""
    quality = 95
    output_buffer = io.BytesIO()
    img.save(output_buffer, format='JPEG', quality=quality)
    current_size = output_buffer.tell()

    while current_size > MAX_FILE_SIZE_BYTES and quality > 10:
        output_buffer.seek(0)
        output_buffer.truncate(0)

        if quality < 60:
            img = img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.LANCZOS)

        quality -= 10
        img.save(output_buffer, format='JPEG', quality=quality)
        current_size = output_buffer.tell()

    return output_buffer.getvalue()


def resize_image_if_needed_bot(image_bytes: bytes) -> bytes:
    """
    (СИНХРОННАЯ) Оптимизированная проверка для бота.
    ВАЖНО: Пропускает видео (MP4, WebM) и GIF без изменений, чтобы не ломать кодировку.
    """
    if not image_bytes: return image_bytes

    if _is_media_format(image_bytes[:12]):
        return image_bytes

    try:
        input_size = len(image_bytes)
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            format_original = img.format

            if getattr(img, "is_animated", False):
                return image_bytes

            needs_resize = _needs_resize_dims(width, height)

            if not needs_resize and input_size <= MAX_FILE_SIZE_BYTES:
                if format_original == 'PNG' and input_size > 5 * 1024 * 1024:
                    pass
                else:
                    return image_bytes

            img = img.convert("RGB")
            new_width, new_height = _calculate_new_dimensions(width, height)

            if new_width != width or new_height != height:
                img = img.resize((new_width, new_height), Image.LANCZOS)

            return _compress_and_save(img)

    except Exception as e:
        return image_bytes


def resize_image_if_needed_site(image_bytes: bytes) -> bytes:
    """
    (СИНХРОННАЯ) Оптимизированная проверка для сайта.
    Отличается тем, что может пересохранять небольшие PNG/WEBP.
    """
    if not image_bytes: return image_bytes

    if _is_media_format(image_bytes[:12]):
        return image_bytes

    try:
        input_size = len(image_bytes)
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            format_original = img.format

            if getattr(img, "is_animated", False):
                return image_bytes

            needs_resize = _needs_resize_dims(width, height)

            if not needs_resize and input_size <= MAX_FILE_SIZE_BYTES:
                if format_original == 'PNG' and input_size > 5 * 1024 * 1024:
                    pass
                else:
                    output_buffer = io.BytesIO()
                    save_fmt = format_original if format_original in ['PNG', 'WEBP'] else 'JPEG'

                    save_img = img
                    if save_fmt == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                        save_img = img.convert("RGB")
                    save_img.save(output_buffer, format=save_fmt, quality=95)
                    return output_buffer.getvalue()

            img = img.convert("RGB")
            new_width, new_height = _calculate_new_dimensions(width, height)

            if new_width != width or new_height != height:
                img = img.resize((new_width, new_height), Image.LANCZOS)

            return _compress_and_save(img)

    except Exception:
        return image_bytes
