import pytest
import re
import abu_engine
import moderation_config

def test_no_illegal_html_chars_in_generators():
    test_inputs = [
        'я пошел в магазин за хлебом и пивом',
        'Ты <script>alert(1)</script> и 1 < 2 & 3 > 2',
        'а' * 1000,
        'https://2ch.hk/b/res/12345.html?foo=bar&baz=qux',
        'a & b < c > d "quotes"',
        '<<<<b>>>></i>',
        "alert('xss')",
    ]

    funcs = [
        abu_engine.generate_bugurt,
        abu_engine.generate_deanon,
        abu_engine.generate_opushchenie,
        abu_engine.generate_psychiatry,
        abu_engine.generate_abu_voice,
        lambda t: abu_engine.transform_abu_mode(t)[1],
    ]

    # Pattern matches valid Telegram tags and valid lowercase entities
    allowed_pat = re.compile(r'</?(?:b|i|code|blockquote|s|u|pre)>|&(?:amp|lt|gt|quot);')

    for f in funcs:
        for inp in test_inputs:
            for _ in range(5):
                res = f(inp)
                assert isinstance(res, str) and res.strip()
                cleaned = allowed_pat.sub('', res)
                # Ensure no raw &, <, > remain
                for ch in ['<', '>', '&']:
                    assert ch not in cleaned, f"Found unescaped '{ch}' in output of {f}: {res}"

def test_adversarial_unicode_and_special_chars():
    adversarial_inputs = [
        "",
        "   \t\n  \r\n  ",
        "\u200b\u200c\u200d\ufeff",
        "\u202eПривет мир двач\u202c",
        "Т̶͐̈́ё̸́с̷т̶ ̶б̸у̵г̵у̵р̶т̸а̵",
        "Привет\x00мир\x00двач",
        "🐵" * 50 + "💩" * 50,
        "!?.!?.!??!!...---,,,:::;;;",
        "А" * 2000,
    ]

    for inp in adversarial_inputs:
        for gen in [
            abu_engine.generate_bugurt,
            abu_engine.generate_deanon,
            abu_engine.generate_opushchenie,
            abu_engine.generate_psychiatry,
            abu_engine.generate_abu_voice,
        ]:
            res = gen(inp)
            assert isinstance(res, str) and len(res) > 0
            assert len(res) < 4000

def test_political_replacements_coverage():
    test_words = [
        'хохол', 'хохла', 'хохлу', 'хохлом', 'хохле',
        'хохлы', 'хохлов', 'хохлам', 'хохлами', 'хохлах',
        'русский', 'русские', 'русских', 'русского', 'русскому',
        'русским', 'русскими', 'русском',
        'русская', 'русской', 'русскую',
        'путин', 'путиным', 'путине', 'пыне', 'пыней',
        'сво', 'cво', 'zvo', 'svo', 'свошник', 'свошники',
        'зеленский', 'зеле', 'зелю', 'зеля'
    ]

    for tw in test_words:
        matched = any(pat.search(tw) for pat, _ in moderation_config.POLITICAL_REPLACEMENTS)
        assert matched, f"Political filter failed to match: {tw}"
