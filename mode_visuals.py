import random
import io
import os
import glob
from typing import Any
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageFilter

TEMPLATE_CONFIG = {
    'gopnik': [
        {
            'filename': 'gopnik1.png',
            'text_area': (107, 143, 423, 267),
            'font_path': 'fonts/Impact.ttf', 'max_font_size': 45, 'text_color': (255, 255, 255),
            'text_align': 'center', 'text_stroke': {'width': 3, 'fill': (0, 0, 0)}
        },
        {
            'filename': 'gopnik2.png',
            'text_area': (24, 332, 487, 487),
            'font_path': 'fonts/Impact.ttf', 'max_font_size': 50, 'text_color': (255, 255, 255),
            'text_align': 'center', 'text_stroke': {'width': 3, 'fill': (0, 0, 0)}
        },
        {
            'filename': 'gopnik3.png',
            'text_area': (65, 333, 457, 460),
            'font_path': 'fonts/Impact.ttf', 'max_font_size': 55, 'text_color': (255, 255, 255),
            'text_align': 'center', 'text_stroke': {'width': 3, 'fill': (0, 0, 0)}
        },
        {
            'filename': 'gopnik4.png',
            'text_area': (40, 347, 479, 485),
            'font_path': 'fonts/Impact.ttf', 'max_font_size': 50, 'text_color': (255, 255, 255),
            'text_align': 'right', 'text_stroke': {'width': 3, 'fill': (0, 0, 0)}
        },
    ],
    'imperial': [
        {
            'filename': 'импер1.png',
            'text_area': (89, 157, 419, 476),
            'font_path': 'fonts/Courier New.ttf', 'max_font_size': 35, 'text_color': (50, 45, 40),
            'text_align': 'left', 'text_stroke': None
        },
        {
            'filename': 'импер2.png',
            'text_area': (130, 104, 424, 339),
            'font_path': 'fonts/Courier New.ttf', 'max_font_size': 40, 'text_color': (40, 35, 30),
            'text_align': 'center', 'text_stroke': None
        },
        {
            'filename': 'импер3.png',
            'text_area': (94, 151, 419, 422),
            'font_path': 'fonts/Courier New.ttf', 'max_font_size': 30, 'text_color': (60, 50, 45),
            'text_align': 'left', 'text_stroke': None
        },
    ],
    'warhammer': [
        {
            'filename': 'ваха1.png',
            'text_area': (112, 110, 396, 401),
            'font_path': 'fonts/ocra.ttf', 'max_font_size': 28, 'text_color': (255, 180, 50),
            'text_align': 'left', 
            'text_stroke': {'width': 1, 'fill': (255, 180, 50, 20)}  
        },
        {
            'filename': 'ваха2.png',
            'text_area': (122, 180, 393, 323),
            'font_path': 'fonts/ocra.ttf', 'max_font_size': 24, 'text_color': (255, 180, 50),
            'text_align': 'left', 
            'text_stroke': {'width': 1, 'fill': (255, 180, 50, 20)}
        },
        {
            'filename': 'ваха3.png',
            'text_area': (170, 208, 345, 304),
            'font_path': 'fonts/ocra.ttf', 'max_font_size': 16, 'text_color': (50, 255, 50),
            'text_align': 'left', 
            'text_stroke': {'width': 1, 'fill': (50, 255, 50, 12)}
        },
    ]
}

DYNAMIC_MODES = {
    'polish': 'templates/polish',
    'ukrainian': 'templates/ukrainian',
    'shizo': 'templates/shizo'
}

FONTS_POOL = ['font1.ttf', 'font2.ttf']

def _wrap_text_by_pixel(draw, text, font, max_width):
    wrapped_lines = []
    user_lines = text.split('\n')
    for line in user_lines:
        if not line:
            wrapped_lines.append('')
            continue
        words = line.split()
        if not words: continue
        current_line = words[0]
        for word in words[1:]:
            if draw.textlength(current_line + " " + word, font=font) <= max_width:
                current_line += " " + word
            else:
                wrapped_lines.append(current_line)
                current_line = word
        wrapped_lines.append(current_line)
    return "\n".join(wrapped_lines)

def _find_best_font_size(draw, text, font_path, max_width, max_height, max_font_size, text_align):
    font = None
    wrapped_text = ""
    for size in range(max_font_size, 12, -2):
        try:
            font = ImageFont.truetype(font_path, size)
        except:
            font = ImageFont.load_default()
        wrapped_text = _wrap_text_by_pixel(draw, text, font, max_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align=text_align)
        if (bbox[3] - bbox[1]) <= max_height:
            return font, wrapped_text
    return font, wrapped_text

@dataclass
class TextDrawConfig:
    font: Any
    fill: tuple
    align: str
    anchor: str
    stroke_width: int = 0

def _draw_text_with_shadow(draw, position, text, config: TextDrawConfig):
    x, y = position
    shadow_color = (0, 0, 0, 180)
    for off_x, off_y in [(-2,-2), (2,-2), (-2,2), (2,2), (0,3)]:
        draw.multiline_text((x+off_x, y+off_y), text, font=config.font, fill=shadow_color, align=config.align, anchor=config.anchor)
    draw.multiline_text(position, text, font=config.font, fill=config.fill, align=config.align, anchor=config.anchor, stroke_width=config.stroke_width, stroke_fill=(0,0,0))

def create_visual_post(mode, text, header=None):
    try:
        img_path = None
        config = None

        if mode in TEMPLATE_CONFIG:
            config = random.choice(TEMPLATE_CONFIG[mode])
            img_path = f"templates/{config['filename']}"
        elif mode in DYNAMIC_MODES:
            folder = DYNAMIC_MODES[mode]
            files = glob.glob(f"{folder}/*.png") + glob.glob(f"{folder}/*.webp")
            if not files: return None
            img_path = random.choice(files)
            
            layout_type = 'bottom' if not header else random.choice(['bottom', 'split'])
            
            config = {
                'font_path': random.choice(FONTS_POOL),
                'text_color': (255, 255, 255),
                'text_align': 'center',
                'layout': layout_type
            }
            if layout_type == 'bottom':
                config['text_area'] = (80, 600, 944, 980)
                config['max_font_size'] = 60
            else:
                config['header_area'] = (80, 40, 944, 180)
                config['text_area'] = (80, 680, 944, 980)
                config['max_font_size'] = 55

        if not img_path or not os.path.exists(img_path): return None
        
        img = Image.open(img_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        
        if mode in DYNAMIC_MODES:
            overlay = Image.new('RGBA', img.size, (0,0,0,0))
            odraw = ImageDraw.Draw(overlay)
            
            if config['layout'] == 'bottom':
                odraw.rectangle([0, 550, 1024, 1024], fill=(0,0,0,130))
            else:
                odraw.rectangle([0, 0, 1024, 200], fill=(0,0,0,130))
                odraw.rectangle([0, 600, 1024, 1024], fill=(0,0,0,130))
            
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

            if config['layout'] == 'split' and header:
                h_x1, h_y1, h_x2, h_y2 = config['header_area']
                clean_h = header.replace("<i>","").replace("</i>","").replace("###","").strip()
                h_font, h_text = _find_best_font_size(draw, clean_h, config['font_path'], h_x2-h_x1, h_y2-h_y1, 40, 'center')
                h_text_config = TextDrawConfig(font=h_font, fill=(255,220,50), align='center', anchor='ma', stroke_width=2)
                _draw_text_with_shadow(draw, (h_x1 + (h_x2-h_x1)/2, h_y1), h_text, h_text_config)

            x1, y1, x2, y2 = config['text_area']
            display_text = text
            if config['layout'] == 'bottom' and header:
                clean_h = header.replace("<i>","").replace("</i>","").replace("###","").strip()
                display_text = f"{clean_h}\n\n{text}"
            
            font, w_text = _find_best_font_size(draw, display_text, config['font_path'], x2-x1, y2-y1, config['max_font_size'], 'center')
            text_config = TextDrawConfig(font=font, fill=(255,255,255), align='center', anchor='ma', stroke_width=2)
            _draw_text_with_shadow(draw, (x1 + (x2-x1)/2, y1), w_text, text_config)

        else:
            x1, y1, x2, y2 = config['text_area']
            full_text = f"{header.replace('<i>','').replace('</i>','')}\n\n{text}" if header else text
            font, w_text = _find_best_font_size(draw, full_text, config['font_path'], x2-x1, y2-y1, config['max_font_size'], config['text_align'])
            pos_x = x1 if config['text_align'] == 'left' else x2 if config['text_align'] == 'right' else x1 + (x2-x1)/2
            anchor = {"left": "la", "center": "ma", "right": "ra"}[config['text_align']]
            stroke_width = config.get('text_stroke', {}).get('width', 0) if config.get('text_stroke') else 0
            text_config = TextDrawConfig(font=font, fill=config['text_color'], align=config['text_align'], anchor=anchor, stroke_width=stroke_width)
            draw.multiline_text((pos_x, y1), w_text, font=text_config.font, fill=text_config.fill, align=text_config.align, anchor=text_config.anchor,
                                stroke_width=text_config.stroke_width,
                                stroke_fill=config.get('text_stroke', {}).get('fill') if config.get('text_stroke') else None)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        return None