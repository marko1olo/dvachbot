import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.text_utils import sanitize_html

# СОСТОЯНИЕ ФАЙЛА (29.07.2026, проверено исполнением, не чтением).
#
# Три теста ниже красные не потому, что ассерты устарели, а потому что в
# common/text_utils.py живут настоящие дефекты. Ассерты оставлены как есть
# СПЕЦИАЛЬНО: sanitize_html — единственный барьер между текстом пользователя и
# HTML публичного сайта, и ослабленный ассерт здесь прячет дыру, а не закрывает её.
#
#   1) test_link_with_attributes / test_link_with_single_quotes и новый
#      test_href_decoy_attribute_does_not_pass_live_anchor.
#      ALLOWED_TAGS_PATTERN (common/text_utils.py:46-51) пропускает тег <a>
#      ДОСЛОВНО со всеми атрибутами, а не пересобирает его из проверенного href.
#      Из-за этого проверка протокола обманывается приманкой в чужом атрибуте:
#      достаточно, чтобы подстрока href="https://..." встретилась где угодно
#      внутри тега. Исполнено: вход
#      <a title="href='https://ok.com'" href="javascript:alert(1)">click</a>
#      возвращается байт в байт, то есть javascript:-ссылка попадает на страницу.
#      Починка: собирать тег заново как '<a href="{проверенный_url}">'.
#
#   2) test_no_protocol_link.
#      Третья альтернатива того же паттерна, '</\s*a\s*>', матчит закрывающий тег
#      БЕЗУСЛОВНО. Исполнено: sanitize_html('</a>') == '</a>', а неразрешённый
#      открывающий тег экранируется — на выходе непарный </a>. Для Telegram
#      (main.py:251 → parse_mode="HTML") это отказ отправки целиком
#      ("Unmatched end tag"), на сайте — досрочное закрытие внешней ссылки.
#      Починка: пускать </a> только при открытом разрешённом <a>, иначе экранировать.
#
# Патч должен лечь в common/text_utils.py. Этому агенту каталог common/ выдан
# как "не трогать" (файл под другим владельцем), поэтому код не правился, а
# тесты оставлены красными как явный сигнал. Не зеленить их правкой ассертов.

class TestSanitizeHtml(unittest.TestCase):
    def test_empty_string(self):
        """Test that empty string and None return empty string."""
        self.assertEqual(sanitize_html(""), "")
        self.assertEqual(sanitize_html(None), "")

    def test_no_links(self):
        """Test that regular text and safe HTML without links is preserved."""
        self.assertEqual(sanitize_html("Just some text"), "Just some text")
        self.assertEqual(sanitize_html("Text with <b>bold</b>"), "Text with <b>bold</b>")

    def test_https_www_link(self):
        """Test standard https://www. link replacement."""
        self.assertEqual(
            sanitize_html('hello <a href="https://www.example.com">my link</a> world'),
            'hello <a href="https://www.example.com">my link</a> world'
        )

    def test_http_link(self):
        """Test standard http:// link replacement."""
        self.assertEqual(
            sanitize_html('hello <a href="http://example.com">my link</a> world'),
            'hello <a href="http://example.com">my link</a> world'
        )

    def test_no_protocol_link(self):
        """
        Ссылка без протокола не должна оставлять после себя непарный </a>.

        КРАСНЫЙ ИЗ-ЗА БАГА КОДА (пункт 2 в заголовке файла). Сейчас возвращается
        'hello &lt;a href="example.com"&gt;my link</a> world': открывающий тег
        экранирован, закрывающий ушёл живым и остался без пары.

        Ожидаемая строка приведена к стратегии экранирования. Прежнее
        'hello my link world' — из той же мёртвой эпохи чёрного списка, что и ассерт
        в test_dangerous_tags_neutralized_by_escaping: вырезание тега вместе с
        разметкой в sanitize_html не делается ни для script, ни для iframe, и
        требовать его только для <a> внутренне противоречиво. Ассерт не ослаблен:
        он требует, чтобы непарный </a> был экранирован, чего код сейчас не делает,
        поэтому тест остаётся красным до правки common/text_utils.py.
        """
        self.assertEqual(
            sanitize_html('hello <a href="example.com">my link</a> world'),
            'hello &lt;a href="example.com"&gt;my link&lt;/a&gt; world'
        )

    def test_link_with_path_and_query(self):
        """Test link with path and query arguments."""
        self.assertEqual(
            sanitize_html('hello <a href="https://example.com/page?test=1">my link</a> world'),
            'hello <a href="https://example.com/page?test=1">my link</a> world'
        )

    def test_link_with_single_quotes(self):
        """
        Тег пересобирается из проверенного href, поэтому кавычки нормализуются.

        КРАСНЫЙ ИЗ-ЗА БАГА КОДА (пункт 1 в заголовке файла). Сам по себе
        одинарные кавычки не уязвимость, но зелёным этот тест станет только когда
        вернётся пересборка тега — та же правка, что закрывает javascript:-обход.
        """
        self.assertEqual(
            sanitize_html("hello <a href='https://example.com'>my link</a> world"),
            'hello <a href="https://example.com">my link</a> world'
        )

    def test_multiple_links(self):
        """Test multiple link replacements in one text block."""
        self.assertEqual(
            sanitize_html('Visit <a href="https://site1.com">site one</a> and <a href="http://www.site2.org/path">site two</a>!'),
            'Visit <a href="https://site1.com">site one</a> and <a href="http://www.site2.org/path">site two</a>!'
        )

    def test_link_with_attributes(self):
        """
        В выводе остаётся только проверенный href, лишние атрибуты срезаются.

        КРАСНЫЙ ИЗ-ЗА БАГА КОДА (пункт 1 в заголовке файла). class/target сами по
        себе безобидны, но пропуск тега дословно — это и есть механизм обхода
        проверки протокола, поэтому ассерт не смягчается до 'лишь бы href был'.
        """
        self.assertEqual(
            sanitize_html('<a class="test" href="https://example.com" target="_blank">link</a>'),
            '<a href="https://example.com">link</a>'
        )

    def test_href_decoy_attribute_does_not_pass_live_anchor(self):
        """
        Приманка href="https://..." в чужом атрибуте не должна легализовать тег.

        НОВЫЙ ТЕСТ, КРАСНЫЙ ИЗ-ЗА БАГА КОДА: исполнено 29.07.2026 — вход
        возвращается без изменений, то есть на публичную страницу уходит
        <a href="javascript:alert(1)">. Дыра не была покрыта ни одним тестом,
        поэтому её и починили бы во второй раз вслепую.

        Ассерт проверяет минимальное истинное свойство: живого <a из этой строки
        быть не должно. Экранировать тег целиком или выбросить — дело починки.
        """
        payload = '<a title="href=\'https://ok.com\'" href="javascript:alert(1)">click</a>'
        self.assertNotIn('<a', sanitize_html(payload))

    def test_dangerous_tags_neutralized_by_escaping(self):
        """
        script/iframe/object обезвреживаются экранированием, а не вырезанием.

        ЕДИНСТВЕННЫЙ УСТАРЕВШИЙ АССЕРТ В ФАЙЛЕ. Раньше ждали 'Hello' — вырезания
        тега вместе с содержимым. sanitize_html с тех пор перешла с чёрного списка
        на белый: RE_SCRIPT_TAG, RE_SCRIPT_SINGLE, RE_DANGEROUS_TAGS и
        RE_DANGEROUS_SINGLE остались объявленными в common/text_utils.py и не
        используются ни одной строкой проекта (проверено rg по всему дереву), а всё,
        чего нет в ALLOWED_TAGS_PATTERN, экранируется. Защита от XSS от этого не
        слабее: '&lt;script&gt;' — текстовый узел, браузер его не исполняет, а
        Telegram при parse_mode="HTML" видит сущность, а не тег. Разница только в
        том, что пользователь теперь видит текст полезной нагрузки.

        Ассерт не ослаблен: сверяем точную строку И отсутствие живого тега, чтобы
        подмена стратегии обратно на 'пропускаем как есть' завалила тест.
        """
        for payload, expected in (
            ('<script>alert("XSS")</script>Hello',
             '&lt;script&gt;alert("XSS")&lt;/script&gt;Hello'),
            ('Check this <iframe src="bad"></iframe> out',
             'Check this &lt;iframe src="bad"&gt;&lt;/iframe&gt; out'),
            ('<object data="flash.swf"></object>Test',
             '&lt;object data="flash.swf"&gt;&lt;/object&gt;Test'),
        ):
            with self.subTest(payload=payload):
                result = sanitize_html(payload)
                self.assertEqual(result, expected)
                lowered = result.lower()
                self.assertNotIn('<script', lowered)
                self.assertNotIn('<iframe', lowered)
                self.assertNotIn('<object', lowered)

    def test_telegram_link_preserved(self):
        """Test that Telegram and Telegraph links are preserved as actual HTML links."""
        self.assertEqual(
            sanitize_html('Check <a href="https://t.me/zakat_2">Gentleman</a> channel'),
            'Check <a href="https://t.me/zakat_2">Gentleman</a> channel'
        )
        self.assertEqual(
            sanitize_html('Read <a href="http://telegra.ph/some-article">article</a> now'),
            'Read <a href="http://telegra.ph/some-article">article</a> now'
        )

if __name__ == '__main__':
    unittest.main()
