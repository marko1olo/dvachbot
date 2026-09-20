import pytest
import io
from PIL import Image
import invite_image_generator as iig

def test_styles_registry():
    """Verify all 16 styles and alias resolution."""
    assert len(iig.INVITE_LAYOUT_STYLES) == 16
    assert len(iig.STYLE_NAMES) == 16
    
    expected_styles = [
        "CYBER_BOARD",
        "DEMOTIVATOR_2CH",
        "CYBER_PLAQUE",
        "VAPOR_NEON",
        "BREAKING_NEWS",
        "ANIME_JAPAN_CARD",
        "TERMINAL_MATRIX",
        "SOVIET_PROPAGANDA",
        "VHS_ANALOG_HORROR",
        "DARK_GOTHIC_SCROLL",
        "BRUTALIST_POSTER",
        "COMIC_BUBBLE",
        "BIOHAZARD_ZONE",
        "ASCII_TERMINAL",
        "Y2K_WIN98",
        "SCHIZO_COLLAGE",
    ]
    for idx, name in enumerate(expected_styles):
        assert iig.STYLE_NAMES[idx] == name
        assert idx in iig.INVITE_LAYOUT_STYLES

def test_alias_resolution():
    """Verify resolve_layout_style maps canonical names, aliases, and integers."""
    assert iig.resolve_layout_style(7) == 7
    assert iig.resolve_layout_style("soviet_propaganda") == 7
    assert iig.resolve_layout_style("SOVIET-PROPAGANDA") == 7
    assert iig.resolve_layout_style("vhs_analog_horror") == 8
    assert iig.resolve_layout_style("analog_horror") == 8
    assert iig.resolve_layout_style("dark_gothic_scroll") == 9
    assert iig.resolve_layout_style("gothic") == 9
    assert iig.resolve_layout_style("brutalist_poster") == 10
    assert iig.resolve_layout_style("comic_bubble") == 11
    assert iig.resolve_layout_style("biohazard_zone") == 12
    assert iig.resolve_layout_style("toxic") == 12
    assert iig.resolve_layout_style("ascii_terminal") == 13
    assert iig.resolve_layout_style("dos") == 13
    assert iig.resolve_layout_style("y2k_win98") == 14
    assert iig.resolve_layout_style("windows98") == 14
    assert iig.resolve_layout_style("schizo_collage") == 15
    assert iig.resolve_layout_style("schizo") == 15
    assert iig.resolve_layout_style("retro_vaporwave") == 3
    assert iig.resolve_layout_style("neon_terminal") == 6
    assert iig.resolve_layout_style("newspaper_frontpage") == 4
    # Unknown fallback
    assert iig.resolve_layout_style("non_existent_style") == 0
    assert iig.resolve_layout_style(999) == 0

def test_slogans_and_companion_texts_collection():
    """Verify collection size and integrity."""
    assert len(iig.IMAGE_SLOGANS) >= 45
    for s in iig.IMAGE_SLOGANS:
        assert "badge" in s and len(s["badge"]) > 0
        assert "headline" in s and len(s["headline"]) > 0
        assert "subline" in s and len(s["subline"]) > 0
        
    assert len(iig.AUTO_POST_COMPANION_TEXTS) >= 15
    for t in iig.AUTO_POST_COMPANION_TEXTS:
        assert isinstance(t, str) and len(t) > 20

def test_clean_text_for_font():
    """Verify clean_text_for_font strips emojis and handles problematic symbols."""
    raw = "🔥 Внимание! 💀 Тгач ⚡ 100% ★ круто!"
    cleaned = iig.clean_text_for_font(raw)
    assert "🔥" not in cleaned
    assert "💀" not in cleaned
    assert "[!]" in cleaned or "!" in cleaned
    assert "*" in cleaned

def test_all_16_styles_rendering_procedural():
    """Verify each layout style renders a valid 800x800 JPEG from procedural background."""
    for style_id in range(16):
        slogan = iig.IMAGE_SLOGANS[style_id % len(iig.IMAGE_SLOGANS)]
        buf = iig.build_invite_image_card(
            base_image=None,
            slogan_dict=slogan,
            board_id="b",
            bot_username="@dvach_chatbot",
            layout_style=style_id
        )
        assert isinstance(buf, io.BytesIO)
        raw = buf.getvalue()
        assert len(raw) > 1000
        
        img = Image.open(io.BytesIO(raw))
        assert img.format == "JPEG"
        assert img.size == (800, 800)

def test_all_16_styles_rendering_with_image():
    """Verify each layout style renders a valid 800x800 JPEG with custom base image."""
    base = Image.new("RGB", (640, 480), color=(100, 150, 200))
    for style_id in range(16):
        buf = iig.build_invite_image_card(
            base_image=base,
            slogan_dict=None,
            custom_text=f"Тестовый заголовок для стиля {style_id}",
            board_id="vg",
            bot_username="@test_bot",
            layout_style=style_id
        )
        assert isinstance(buf, io.BytesIO)
        img = Image.open(io.BytesIO(buf.getvalue()))
        assert img.format == "JPEG"
        assert img.size == (800, 800)

def test_get_random_auto_invite_content():
    """Verify get_random_auto_invite_content returns valid slogan and formatted text."""
    slogan, caption = iig.get_random_auto_invite_content("b", "@test_bot")
    assert isinstance(slogan, dict)
    assert "headline" in slogan
    assert isinstance(caption, str)
    assert len(caption) > 20
    assert "@" in caption or "QR" in caption or "Тгач" in caption or "тгач" in caption or "доск" in caption or "код" in caption

def test_render_custom_demotivator():
    """Verify custom demotivator renders properly."""
    buf = iig.render_custom_demotivator(
        base_image=None,
        title="ШИЗОФРЕНИЯ",
        subtitle="Это не баг, это фича",
        bot_username="@dvach_chatbot"
    )
    assert isinstance(buf, io.BytesIO)
    img = Image.open(io.BytesIO(buf.getvalue()))
    assert img.format == "JPEG"
    assert img.size == (800, 850)

@pytest.mark.asyncio
async def test_generate_invite_image_async():
    """Verify async generation works without blocking."""
    buf = await iig.generate_invite_image_async(
        board_id="b",
        bot_username="@dvach_chatbot",
        layout_style="soviet_propaganda"
    )
    assert isinstance(buf, io.BytesIO)
    img = Image.open(io.BytesIO(buf.getvalue()))
    assert img.size == (800, 800)
