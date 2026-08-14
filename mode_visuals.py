import random
import io
import os
import glob
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

@dataclass
class FontFitConfig:
    font_path: str
    max_width: int
    max_height: int
    max_font_size: int
    text_align: str

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
    'shizo': 'templates/shizo',
    'zaputin': 'templates/zaputin',
    'gopnik': 'templates/gopnik'
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

def _find_best_font_size(draw, text, fit_config: FontFitConfig):
    font = None
    wrapped_text = ""
    for size in range(fit_config.max_font_size, 12, -2):
        try:
            font = ImageFont.truetype(fit_config.font_path, size)
        except:
            font = ImageFont.load_default()
        wrapped_text = _wrap_text_by_pixel(draw, text, font, fit_config.max_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align=fit_config.text_align)
        if (bbox[3] - bbox[1]) <= fit_config.max_height:
            return font, wrapped_text
    return font, wrapped_text

def _draw_text_with_shadow(draw, position, text, **kwargs):
    x, y = position
    shadow_color = (0, 0, 0, 180)

    fill = kwargs.pop('fill', None)
    stroke_width = kwargs.pop('stroke_width', 0)
    stroke_fill = kwargs.pop('stroke_fill', (0, 0, 0))

    for off_x, off_y in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)]:
        draw.multiline_text((x+off_x, y+off_y), text, fill=shadow_color, **kwargs)

    draw.multiline_text(position, text, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill, **kwargs)

def create_visual_post(mode, text, header=None):
    try:
        img_path = None
        config = None

        if mode in TEMPLATE_CONFIG:
            config = random.choice(TEMPLATE_CONFIG[mode])
            img_path = f"templates/{config['filename']}"
        elif mode in DYNAMIC_MODES:
            folder = DYNAMIC_MODES[mode]
            files = (glob.glob(f"{folder}/*.png") + 
                     glob.glob(f"{folder}/*.webp") + 
                     glob.glob(f"{folder}/*.jpg") + 
                     glob.glob(f"{folder}/*.jpeg"))
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
                config['text_area'] = (60, 550, 964, 870)
                config['max_font_size'] = 55
            else:
                config['header_area'] = (60, 40, 964, 180)
                config['text_area'] = (60, 600, 964, 870)
                config['max_font_size'] = 50

        if not img_path or not os.path.exists(img_path): return None
        
        img = Image.open(img_path).convert("RGBA")
        if img.size != (1024, 1024):
            # Guarantee 1024x1024 1:1 square
            if abs(img.width - img.height) > 20:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                new_sq = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
                new_sq.paste(img, ((1024 - img.width) // 2, (1024 - img.height) // 2))
                img = new_sq
            else:
                img = img.resize((1024, 1024), Image.Resampling.LANCZOS)

        draw = ImageDraw.Draw(img)
        
        if mode in DYNAMIC_MODES:
            def get_font_by_size(size: int, bold: bool = True):
                for p in ["fonts/Impact.ttf", 
                          "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf", 
                          "C:/Windows/Fonts/impact.ttf", 
                          "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"]:
                    if os.path.exists(p):
                        try: return ImageFont.truetype(p, size)
                        except Exception: pass
                return ImageFont.load_default()

            clean_h = ""
            if header:
                clean_h = header.replace("<i>", "").replace("</i>", "").replace("###", "").strip()
                for em in ["💙", "💛", "🇺🇦", "🚜", "🐷", "🔥", "✈️", "💥", "👑", "⚡", "🎯", "🇵🇱", "🧠"]:
                    clean_h = clean_h.replace(em, "").strip()

            def wrap_text_str(odraw, txt, font, max_w):
                words = txt.split()
                lines, curr = [], ""
                for w in words:
                    test = f"{curr} {w}".strip()
                    if odraw.textlength(test, font=font) <= max_w:
                        curr = test
                    else:
                        if curr: lines.append(curr)
                        curr = w
                if curr: lines.append(curr)
                return "\n".join(lines)

            # Pick style from 8 elite meme layout styles
            available_styles = [
                'cyber_banner', 'breaking_news', 'speech_bubble', 'demotivator',
                'impact_bold', 'neon_cyberpunk_glitch', 'retro_window',
                'gopnik_quote', 'propaganda_banner', 'cctv_camera'
            ]
            style = random.choice(available_styles)

            # 1. BREAKING NEWS STYLE
            if style == 'breaking_news':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                f_ticker = get_font_by_size(24)
                f_text = get_font_by_size(36)
                
                if mode == 'ukrainian':
                    banner_title = "ТЕРМІНОВА БАВОВНА | ТГАЧ NEWS 24/7"
                    bg_col = (20, 40, 70, 240)
                    top_bar = (0, 140, 255, 255)
                elif mode == 'zaputin':
                    banner_title = "СРОЧНАЯ СВОДКА С ФРОНТА | ТГАЧ Z-NEWS"
                    bg_col = (40, 15, 15, 240)
                    top_bar = (220, 30, 20, 255)
                else:
                    banner_title = "СРОЧНАЯ МОЛНИЯ | ТГАЧ NEWS 24/7"
                    bg_col = (10, 14, 22, 235)
                    top_bar = (220, 35, 45, 255)

                odraw.rectangle([0, 560, 1024, 760], fill=bg_col)
                odraw.rectangle([0, 560, 1024, 606], fill=top_bar)
                odraw.text((32, 572), banner_title, font=f_ticker, fill=(255, 255, 255, 255))
                
                wrapped = wrap_text_str(odraw, text, f_text, 960)
                img = Image.alpha_composite(img, overlay)
                draw = ImageDraw.Draw(img)
                draw.multiline_text((32, 626), wrapped, font=f_text, fill=(255, 235, 60, 255))

            # 2. COMIC SPEECH BUBBLE
            elif style == 'speech_bubble':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                f_text = get_font_by_size(34)
                wrapped = wrap_text_str(odraw, text, f_text, 760)
                
                bbox = odraw.multiline_textbbox((0, 0), wrapped, font=f_text, align="center")
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                bx, by, bw, bh = 100, 480, 824, min(240, th + 50)
                
                if mode == 'ukrainian':
                    border_c = (0, 140, 255, 255)
                elif mode == 'zaputin':
                    border_c = (220, 30, 20, 255)
                else:
                    border_c = (255, 60, 60, 255)

                odraw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=22, fill=(255, 255, 255, 245), outline=border_c, width=3)
                odraw.polygon([(bx + 80, by), (bx + 110, by - 30), (bx + 140, by)], fill=(255, 255, 255, 245), outline=border_c)
                
                img = Image.alpha_composite(img, overlay)
                draw = ImageDraw.Draw(img)
                tx = bx + (bw - tw)/2
                ty = by + (bh - th)/2
                draw.multiline_text((tx, ty), wrapped, font=f_text, fill=(15, 20, 30, 255), align="center")

            # 3. DEMOTIVATOR EMBED
            elif style == 'demotivator':
                canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
                inner_w, inner_h = 860, 580
                inner_img = img.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
                canvas.paste(inner_img, (82, 60))
                draw = ImageDraw.Draw(canvas)
                draw.rectangle([78, 56, 78 + inner_w + 8, 56 + inner_h + 8], outline=(255, 255, 255, 255), width=2)
                
                f_dem_head = get_font_by_size(42)
                f_dem_sub = get_font_by_size(24, bold=False)
                
                if mode == 'ukrainian':
                    def_head = "СЛАВА УКРАЇНІ!"
                elif mode == 'zaputin':
                    def_head = "ГОЙДА, БРАТЬЯ!"
                else:
                    def_head = "БАЗА ДВАЧА"

                head_txt = clean_h if clean_h else def_head
                hw = draw.textlength(head_txt, font=f_dem_head)
                draw.text(((1024 - hw)/2, 680), head_txt, font=f_dem_head, fill=(255, 215, 40, 255))
                
                wrapped = wrap_text_str(draw, text, f_dem_sub, 860)
                tb = draw.multiline_textbbox((0, 0), wrapped, font=f_dem_sub, align="center")
                tw = tb[2] - tb[0]
                draw.multiline_text(((1024 - tw)/2, 745), wrapped, font=f_dem_sub, fill=(255, 255, 255, 255), align="center")
                img = canvas

            # 4. IMPACT BOLD MEME
            elif style == 'impact_bold':
                draw = ImageDraw.Draw(img)
                f_impact = get_font_by_size(50)
                words = text.split()
                if len(words) > 4:
                    mid = len(words) // 2
                    top_txt = " ".join(words[:mid])
                    bot_txt = " ".join(words[mid:])
                else:
                    top_txt = clean_h if clean_h else ("СЛАВА УКРАЇНІ!" if mode == 'ukrainian' else "БАЗИРОВАННЫЙ ПОСТ")
                    bot_txt = text
                
                tw1 = draw.textlength(top_txt, font=f_impact)
                tx1, ty1 = (1024 - tw1)/2, 60
                for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)]:
                    draw.text((tx1+ox, ty1+oy), top_txt, font=f_impact, fill=(0, 0, 0, 255))
                draw.text((tx1, ty1), top_txt, font=f_impact, fill=(255, 255, 255, 255))
                
                tw2 = draw.textlength(bot_txt, font=f_impact)
                tx2, ty2 = (1024 - tw2)/2, 680
                for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)]:
                    draw.text((tx2+ox, ty2+oy), bot_txt, font=f_impact, fill=(0, 0, 0, 255))
                draw.text((tx2, ty2), bot_txt, font=f_impact, fill=(255, 230, 40, 255))

            # 5. NEON CYBERPUNK GLITCH
            elif style == 'neon_cyberpunk_glitch':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                by1, by2 = 560, 770
                odraw.rectangle([40, by1, 984, by2], fill=(8, 12, 20, 220), outline=(0, 240, 255, 220), width=2)
                for gy in range(by1 + 6, by2, 8):
                    odraw.line([(42, gy), (982, gy)], fill=(0, 0, 0, 80), width=1)
                odraw.line([(32, by1 - 8), (56, by1 - 8)], fill=(255, 0, 120, 255), width=3)
                odraw.line([(32, by1 - 8), (32, by1 + 16)], fill=(255, 0, 120, 255), width=3)
                odraw.line([(992, by2 + 8), (968, by2 + 8)], fill=(0, 240, 255, 255), width=3)
                odraw.line([(992, by2 + 8), (992, by2 - 16)], fill=(0, 240, 255, 255), width=3)
                
                f_tag = get_font_by_size(14, bold=True)
                odraw.text((54, by1 + 10), "[ SYSTEM_OVERRIDE // V2.077 ]", font=f_tag, fill=(0, 255, 200, 255))

                f_txt = get_font_by_size(36)
                wrapped = wrap_text_str(odraw, text, f_txt, 900)
                tb = odraw.multiline_textbbox((0, 0), wrapped, font=f_txt, align="center")
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                tx = (1024 - tw) / 2
                ty = by1 + 42 + (by2 - by1 - 42 - th) / 2

                odraw.multiline_text((tx - 3, ty), wrapped, font=f_txt, fill=(0, 240, 255, 200), align="center")
                odraw.multiline_text((tx + 3, ty), wrapped, font=f_txt, fill=(255, 0, 120, 200), align="center")
                odraw.multiline_text((tx, ty), wrapped, font=f_txt, fill=(255, 255, 255, 255), align="center")
                img = Image.alpha_composite(img, overlay)

            # 6. RETRO WINDOWS 95 DIALOG
            elif style == 'retro_window':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                wx, wy, ww, wh = 80, 520, 864, 250
                odraw.rectangle([wx, wy, wx + ww, wy + wh], fill=(195, 199, 203, 250), outline=(255, 255, 255, 255), width=2)
                odraw.line([(wx + ww, wy), (wx + ww, wy + wh)], fill=(0, 0, 0, 255), width=2)
                odraw.line([(wx, wy + wh), (wx + ww, wy + wh)], fill=(0, 0, 0, 255), width=2)
                
                title_bar_col = (0, 0, 128, 255) if mode != 'zaputin' else (140, 0, 0, 255)
                odraw.rectangle([wx + 4, wy + 4, wx + ww - 4, wy + 38], fill=title_bar_col)
                f_wtitle = get_font_by_size(18, bold=True)
                w_title = clean_h if clean_h else "Critical Alert - ТГАЧ 95"
                odraw.text((wx + 12, wy + 10), w_title, font=f_wtitle, fill=(255, 255, 255, 255))
                odraw.rectangle([wx + ww - 32, wy + 8, wx + ww - 10, wy + 30], fill=(195, 199, 203, 255), outline=(0, 0, 0, 255))
                odraw.text((wx + ww - 26, wy + 9), "X", font=f_wtitle, fill=(0, 0, 0, 255))

                odraw.ellipse([wx + 24, wy + 60, wx + 74, wy + 110], fill=(240, 200, 30, 255), outline=(0, 0, 0, 255), width=2)
                odraw.text((wx + 44, wy + 66), "!", font=get_font_by_size(32, bold=True), fill=(0, 0, 0, 255))

                f_msg = get_font_by_size(28, bold=True)
                wrapped = wrap_text_str(odraw, text, f_msg, 720)
                odraw.multiline_text((wx + 96, wy + 62), wrapped, font=f_msg, fill=(0, 0, 0, 255))

                btn_x, btn_y, btn_w, btn_h = wx + (ww - 120)//2, wy + wh - 48, 120, 36
                odraw.rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], fill=(220, 224, 228, 255), outline=(0, 0, 0, 255), width=2)
                odraw.text((btn_x + 44, btn_y + 8), "OK", font=f_wtitle, fill=(0, 0, 0, 255))
                img = Image.alpha_composite(img, overlay)

            # 7. GOPNIK / ANON QUOTE CARD
            elif style == 'gopnik_quote':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                for y in range(480, 1024):
                    alpha = int(((y - 480) / (1024 - 480)) ** 1.3 * 235)
                    odraw.line([(0, y), (1024, y)], fill=(8, 10, 14, alpha), width=1)
                    
                f_quote = get_font_by_size(36, bold=True)
                wrapped = wrap_text_str(odraw, f"«{text}»", f_quote, 880)
                tb = odraw.multiline_textbbox((0, 0), wrapped, font=f_quote, align="center")
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                tx = (1024 - tw) / 2
                ty = 600
                
                for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, 3)]:
                    odraw.multiline_text((tx + ox, ty + oy), wrapped, font=f_quote, fill=(0, 0, 0, 255), align="center")
                odraw.multiline_text((tx, ty), wrapped, font=f_quote, fill=(255, 225, 75, 255), align="center")

                f_sign = get_font_by_size(18, bold=True)
                author_txt = f"© {clean_h}" if clean_h else "© Анон из /b/, золотые мысли борды"
                aw = odraw.textlength(author_txt, font=f_sign)
                odraw.text(((1024 - aw)/2, ty + th + 24), author_txt, font=f_sign, fill=(180, 190, 205, 220))
                img = Image.alpha_composite(img, overlay)

            # 8. PROPAGANDA CONSTRUCTIVIST BANNER
            elif style == 'propaganda_banner':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                poly = [(0, 540), (1024, 500), (1024, 760), (0, 800)]
                stripe_col = (200, 30, 25, 245) if mode != 'ukrainian' else (0, 100, 220, 245)
                odraw.polygon(poly, fill=stripe_col, outline=(255, 220, 40, 255))
                odraw.polygon([(0, 532), (1024, 492), (1024, 502), (0, 542)], fill=(255, 220, 40, 255))

                f_prop = get_font_by_size(40, bold=True)
                wrapped = wrap_text_str(odraw, text, f_prop, 920)
                tb = odraw.multiline_textbbox((0, 0), wrapped, font=f_prop, align="center")
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                tx = (1024 - tw)/2
                ty = 580
                for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)]:
                    odraw.multiline_text((tx + ox, ty + oy), wrapped, font=f_prop, fill=(0, 0, 0, 255), align="center")
                odraw.multiline_text((tx, ty), wrapped, font=f_prop, fill=(255, 235, 50, 255), align="center")
                img = Image.alpha_composite(img, overlay)

            # 9. CCTV SECURITY CAMERA
            elif style == 'cctv_camera':
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                f_hud = get_font_by_size(18, bold=True)
                odraw.text((40, 36), "CAM_07 [LIVE] • 24 FPS", font=f_hud, fill=(0, 255, 120, 240))
                odraw.text((1024 - 310, 36), "2026-08-15 01:24:19 UTC", font=f_hud, fill=(0, 255, 120, 240))
                
                odraw.line([(512 - 20, 512), (512 + 20, 512)], fill=(0, 255, 120, 160), width=2)
                odraw.line([(512, 512 - 20), (512, 512 + 20)], fill=(0, 255, 120, 160), width=2)
                
                for gy in range(0, 1024, 6):
                    odraw.line([(0, gy), (1024, gy)], fill=(0, 0, 0, 45), width=1)

                odraw.rectangle([40, 590, 984, 760], fill=(10, 18, 12, 230), outline=(0, 255, 120, 220), width=2)
                odraw.text((56, 604), "[ОБНАРУЖЕНА АКТИВНОСТЬ НА КАМЕРЕ]:", font=get_font_by_size(16, bold=True), fill=(0, 255, 120, 255))
                
                f_msg = get_font_by_size(32, bold=True)
                wrapped = wrap_text_str(odraw, text, f_msg, 900)
                odraw.multiline_text((56, 640), wrapped, font=f_msg, fill=(240, 255, 240, 255))
                img = Image.alpha_composite(img, overlay)

            # 10. CYBER GLASS BANNER (DEFAULT)
            else:
                overlay = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                
                f_size = 42 if len(text) < 60 else (34 if len(text) < 120 else 26)
                f_text = get_font_by_size(f_size)
                f_head = get_font_by_size(24)
                
                wrapped_text = wrap_text_str(odraw, text, f_text, 860)
                bbox = odraw.multiline_textbbox((0, 0), wrapped_text, font=f_text, align="center")
                text_h = bbox[3] - bbox[1]
                
                banner_pad = 22
                head_h = 40 if clean_h else 0
                total_content_h = head_h + text_h
                
                banner_bottom = min(770, max(620, 520 + total_content_h // 2))
                banner_top = max(380, banner_bottom - total_content_h - banner_pad * 2)
                
                border_color = (0, 180, 255, 140) if mode == 'ukrainian' else (255, 100, 100, 140)
                odraw.rounded_rectangle([40, banner_top, 984, banner_bottom], radius=18, fill=(10, 14, 20, 205), outline=border_color, width=2)
                
                img = Image.alpha_composite(img, overlay)
                draw = ImageDraw.Draw(img)
                
                curr_y = banner_top + banner_pad
                if clean_h:
                    h_w = draw.textlength(clean_h, font=f_head)
                    draw.text(((1024 - h_w)/2, curr_y), clean_h, font=f_head, fill=(255, 220, 40, 255))
                    curr_y += head_h
                    
                t_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=f_text, align="center")
                t_w = t_bbox[2] - t_bbox[0]
                t_x = (1024 - t_w) / 2
                
                draw.multiline_text((t_x, curr_y), wrapped_text, font=f_text, fill=(255, 255, 255, 255), align="center")

        else:
            x1, y1, x2, y2 = config['text_area']
            full_text = f"{header.replace('<i>','').replace('</i>','')}\n\n{text}" if header else text
            fit_config = FontFitConfig(
                font_path=config['font_path'],
                max_width=x2-x1,
                max_height=y2-y1,
                max_font_size=config['max_font_size'],
                text_align=config['text_align']
            )
            font, w_text = _find_best_font_size(draw, full_text, fit_config)
            pos_x = x1 if config['text_align'] == 'left' else x2 if config['text_align'] == 'right' else x1 + (x2-x1)/2
            anchor = {"left": "la", "center": "ma", "right": "ra"}[config['text_align']]
            draw.multiline_text((pos_x, y1), w_text, font=font, fill=config['text_color'], align=config['text_align'], anchor=anchor, 
                                stroke_width=config.get('text_stroke', {}).get('width', 0) if config.get('text_stroke') else 0,
                                stroke_fill=config.get('text_stroke', {}).get('fill') if config.get('text_stroke') else None)

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()

    except Exception:
        return None