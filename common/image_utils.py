import io
import os
import random
from PIL import Image, ImageDraw, ImageFont
import numpy as np

FONTS_CACHE = []
try:
    font_files = ["font1.ttf", "font2.ttf", "font3.ttf", "font4.ttf"]
    for ff in font_files:
        if os.path.exists(ff):
            FONTS_CACHE.append(ImageFont.truetype(ff, 40))
    if not FONTS_CACHE:
        FONTS_CACHE.append(ImageFont.load_default())
except Exception:
    FONTS_CACHE.append(ImageFont.load_default())

def smart_wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """
    Переносит текст по словам, основываясь на реальной пиксельной ширине.
    """
    wrapped_lines = []
    user_lines = text.split('\n')
    for line in user_lines:
        if not line:
            wrapped_lines.append('')
            continue
        words = line.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            if draw.textlength(test_line, font=font) <= max_width:
                current_line += word + " "
            else:
                wrapped_lines.append(current_line.strip())
                current_line = word + " "
        wrapped_lines.append(current_line.strip())
    return "\n".join(wrapped_lines)

def _get_fallback_error_image(image_size: tuple[int, int], background_color: tuple[int, int, int]) -> bytes | None:
    error_img = Image.new('RGB', image_size, background_color)
    draw = ImageDraw.Draw(error_img)
    try:
        error_font = ImageFont.load_default()
    except Exception:
        return None
    draw.multiline_text(
        (50, 200), "ERROR:\nFONTS NOT FOUND",
        fill=(255, 50, 50), font=error_font, align="center"
    )
    buffer = io.BytesIO()
    error_img.save(buffer, format='PNG')
    return buffer.getvalue()

def _create_text_layer(text: str, font: ImageFont.FreeTypeFont, image_size: tuple[int, int], text_color: tuple[int, int, int]) -> Image.Image:
    temp_img = Image.new('RGBA', image_size, (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    max_text_width = image_size[0] - 40
    wrapped_text = smart_wrap_text(temp_draw, text, font, max_text_width)

    text_layer = Image.new('RGBA', image_size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)
    draw.multiline_text(
        (image_size[0] / 2, image_size[1] / 2),
        wrapped_text,
        font=font,
        fill=text_color,
        anchor="mm",
        align="center"
    )
    angle = random.uniform(-15, 15)
    return text_layer.rotate(angle, expand=False, resample=Image.BICUBIC)

def _apply_wave_distortion(image: Image.Image) -> Image.Image:
    img_array = np.array(image)
    rows, cols, channels = img_array.shape
    amplitude = random.uniform(3, 10)
    frequency = random.uniform(0.05, 0.1)

    x_indices = np.arange(cols)
    y_offsets = (amplitude * np.sin(x_indices * frequency)).astype(int)

    y_indices = np.arange(rows).reshape(-1, 1) + y_offsets.reshape(1, -1)
    y_indices = np.clip(y_indices, 0, rows - 1)

    distorted_array = np.zeros_like(img_array)
    for x in range(cols):
        shift = y_offsets[x]
        if shift > 0:
            distorted_array[shift:, x] = img_array[:-shift, x]
        elif shift < 0:
            distorted_array[:shift, x] = img_array[-shift:, x]
        else:
            distorted_array[:, x] = img_array[:, x]

    return Image.fromarray(distorted_array, 'RGBA')

def _add_noise(image: Image.Image, image_size: tuple[int, int]) -> Image.Image:
    noise_array = np.random.randint(0, 50, (image_size[1], image_size[0]), dtype=np.uint8)
    noise_layer = Image.fromarray(noise_array, 'L').convert('RGBA')
    noise_layer.putalpha(Image.new('L', image_size, 30))
    return Image.alpha_composite(image, noise_layer)

def generate_wipe_image(text: str) -> bytes | None:
    """
    Создает изображение 512x512 с текстом, искажениями и шумом.
    Исправлена ошибка DeprecationWarning для Pillow 10+.
    """
    try:
        IMAGE_SIZE = (512, 512)
        BACKGROUND_COLOR = (20, 20, 20)
        TEXT_COLOR = (240, 240, 240)

        if not FONTS_CACHE:
            print("⛔ КРИТИЧЕСКАЯ ОШИБКА: Шрифты не загружены (FONTS_CACHE пуст)!")
            return _get_fallback_error_image(IMAGE_SIZE, BACKGROUND_COLOR)

        background = Image.new('RGBA', IMAGE_SIZE, BACKGROUND_COLOR)
        font = random.choice(FONTS_CACHE)

        rotated_text_layer = _create_text_layer(text, font, IMAGE_SIZE, TEXT_COLOR)
        distorted_layer = _apply_wave_distortion(rotated_text_layer)
        background.alpha_composite(distorted_layer)

        final_image = _add_noise(background, IMAGE_SIZE)

        buffer = io.BytesIO()
        final_image.convert("RGB").save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as e:
        print(f"⛔ КРИТИЧЕСКАЯ ОШИБКА в generate_wipe_image: {e}")
        import traceback
        traceback.print_exc()
        return None
