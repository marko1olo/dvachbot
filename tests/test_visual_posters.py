# -*- coding: utf-8 -*-
"""
tests/test_visual_posters.py — Visual Quality, Pixel Verification & Typography Test Suite.
Validates:
1. All 4 category posters render valid PNG images with non-zero entropy and valid dimensions.
2. Personal 2ch Wrapped cards render without errors for active and ghost users.
3. Absence of NaN / None / null / undefined string leaks.
4. Matplotlib memory safety (plt.get_fignums() == 0 after renders).
5. Theme palette contrast ratios against dark backgrounds.
"""

import io
import math
import warnings
from PIL import Image, ImageStat
import pytest

import stats_v2
import my_wrapped_generator

def calculate_shannon_entropy(im: Image.Image) -> float:
    histogram = im.convert("L").histogram()
    total_pixels = sum(histogram)
    if total_pixels == 0:
        return 0.0
    entropy = 0.0
    for count in histogram:
        if count > 0:
            p = count / total_pixels
            entropy -= p * math.log2(p)
    return entropy

def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def get_relative_luminance(rgb: tuple) -> float:
    srgb = [v / 255.0 for v in rgb]
    lum = []
    for c in srgb:
        if c <= 0.03928:
            lum.append(c / 12.92)
        else:
            lum.append(((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lum[0] + 0.7152 * lum[1] + 0.0722 * lum[2]

def calculate_contrast_ratio(rgb1: tuple, rgb2: tuple) -> float:
    l1 = get_relative_luminance(rgb1)
    l2 = get_relative_luminance(rgb2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def test_theme_palette_contrast():
    """Verify theme palette contrast against dark background (#0b0f17)."""
    bg_rgb = hex_to_rgb(stats_v2.THEME_BG)
    palette = [
        ("COLOR_TEXT_MAIN", stats_v2.COLOR_TEXT_MAIN, 10.0),
        ("COLOR_TEXT_MUTED", stats_v2.COLOR_TEXT_MUTED, 4.5),
        ("COLOR_CYAN", stats_v2.COLOR_CYAN, 4.5),
        ("COLOR_PINK", stats_v2.COLOR_PINK, 4.5),
        ("COLOR_GREEN", stats_v2.COLOR_GREEN, 4.5),
        ("COLOR_AMBER", stats_v2.COLOR_AMBER, 4.5),
        ("COLOR_BLUE", stats_v2.COLOR_BLUE, 4.5),
    ]
    for name, hex_val, min_ratio in palette:
        rgb = hex_to_rgb(hex_val)
        ratio = calculate_contrast_ratio(rgb, bg_rgb)
        assert ratio >= min_ratio, f"Color {name} ({hex_val}) contrast {ratio:.2f}:1 is below {min_ratio}:1"


@pytest.mark.parametrize("generator_func,category_name", [
    (stats_v2.generate_economy_heists_poster, "economy"),
    (stats_v2.generate_pvp_bioweapons_poster, "pvp"),
    (stats_v2.generate_bayan_memetics_poster, "memetics"),
    (stats_v2.generate_drama_beef_poster, "drama"),
])
def test_category_posters_rendering(generator_func, category_name):
    """Verify all category posters render valid PNG images with non-zero entropy."""
    buf = generator_func()
    assert isinstance(buf, io.BytesIO)
    raw_bytes = buf.getvalue()
    assert len(raw_bytes) > 5000, f"Poster {category_name} file size too small ({len(raw_bytes)} bytes)"

    im = Image.open(buf)
    assert im.format == "PNG"
    w, h = im.size
    assert w >= 1000 and h >= 500, f"Poster {category_name} dimensions too small: {w}x{h}"

    entropy = calculate_shannon_entropy(im)
    assert entropy > 1.5, f"Poster {category_name} entropy too low ({entropy:.2f} bits/px), likely blank"


def test_instant_snapshot_text_and_sparklines():
    """Verify snapshot text contains ASCII sparklines and zero NaN/None leaks."""
    text, data = stats_v2.generate_instant_snapshot_text()
    assert isinstance(text, str) and len(text) > 50
    assert "ДВАЧ-АНАЛИТИКА V2" in text
    assert any(b in text for b in stats_v2.SPARK_BARS), "Snapshot text missing ASCII sparkline characters"

    for forbidden in ["NaN", "None", "null", "undefined"]:
        assert forbidden not in text, f"Found forbidden leak '{forbidden}' in snapshot text"


def test_wrapped_card_rendering_active_user():
    """Verify Wrapped card renders properly for existing user."""
    buf = my_wrapped_generator.generate_my_wrapped_poster(0)
    assert isinstance(buf, io.BytesIO)
    im = Image.open(buf)
    assert im.format == "PNG"
    entropy = calculate_shannon_entropy(im)
    assert entropy > 1.2


def test_wrapped_card_rendering_ghost_user():
    """Verify Wrapped card handles new users with 0 activity gracefully without throwing TypeError."""
    buf = my_wrapped_generator.generate_my_wrapped_poster(999999999)
    assert isinstance(buf, io.BytesIO)
    im = Image.open(buf)
    assert im.format == "PNG"
    entropy = calculate_shannon_entropy(im)
    assert entropy > 1.0


def test_matplotlib_memory_safety():
    """Verify all figure resources are closed after rendering."""
    import matplotlib.pyplot as plt
    assert len(plt.get_fignums()) == 0, f"Detected unclosed matplotlib figures: {plt.get_fignums()}"

