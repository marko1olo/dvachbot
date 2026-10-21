# -*- coding: utf-8 -*-
"""
Tests for LaTeX normalization and text chunking / split improvements.
"""

import pytest
from common.latex_utils import normalize_latex, to_superscript, to_subscript
from common.html_utils import convert_site_tags_to_telegram
from utils import split_text
from common.text_chunker import count_tg_utf16_units, chunk_html_message


class TestLatexNormalization:
    def test_greek_letters(self):
        assert normalize_latex(r"\alpha + \beta = \gamma") == "α + β = γ"
        assert normalize_latex(r"\Delta G \lt 0") == "ΔG < 0"
        assert normalize_latex(r"\Omega \cdot \mu") == "Ω · μ"
        assert normalize_latex(r"\pi \approx 3.14159") == "π ≈ 3.14159"

    def test_superscripts_and_exponents(self):
        assert normalize_latex(r"E = mc^2") == "E = mc²"
        assert normalize_latex(r"3 \times 10^{11}") == "3 × 10¹¹"
        assert normalize_latex(r"10^7–10^8") == "10⁷–10⁸"
        assert normalize_latex(r"10^3\text{–}10^4") == "10³–10⁴"
        assert normalize_latex(r"E^\circ = +0.82\text{ В}") == "E° = +0.82 В"
        assert normalize_latex(r"\Delta V^\ddagger \lt 0") == "ΔV‡ < 0"

    def test_subscripts_and_chemicals(self):
        assert normalize_latex(r"\text{CO}_2") == "CO₂"
        assert normalize_latex(r"\text{H}_2\text{O} + \text{NH}_3") == "H₂O + NH₃"
        assert normalize_latex(r"\text{Mn}_4\text{CaO}_5") == "Mn₄CaO₅"
        assert normalize_latex(r"\text{scCO}_2") == "scCO₂"
        assert normalize_latex(r"f_p \cdot n_e \cdot f_l \cdot f_i") == "fₚ · nₑ · fₗ · fᵢ"
        assert normalize_latex(r"E_a / RT") == "Eₐ / RT"

    def test_escaped_characters(self):
        assert normalize_latex(r"85\%") == "85%"
        assert normalize_latex(r"99.99\%") == "99.99%"
        assert normalize_latex(r"\$100") == "$100"
        assert normalize_latex(r"foo\_bar") == "foo_bar"

    def test_math_operators_and_fractions(self):
        assert normalize_latex(r"\exp(-E_a/RT)") == "exp(-Eₐ/RT)"
        assert normalize_latex(r"\ln(x) + \sin(\theta)") == "ln(x) + sin(θ)"
        assert normalize_latex(r"\frac{1}{2}") == "(1)/(2)"
        assert normalize_latex(r"\sqrt{a^2 + b^2}") == "√(a² + b²)"

    def test_text_wrappers_and_formatting(self):
        assert normalize_latex(r"\text{Fe, Si, Mg, P}") == "Fe, Si, Mg, P"
        assert normalize_latex(r"5\text{–}10\text{ миллиардов}") == "5–10 миллиардов"
        assert normalize_latex(r"\textbf{важно}") == "<b>важно</b>"
        assert normalize_latex(r"\textit{курсив}") == "<i>курсив</i>"

    def test_preserves_code_identifiers_and_paths(self):
        # snake_case identifiers must NOT be mangled
        assert normalize_latex("def get_user_id(chat_id): return user_id") == "def get_user_id(chat_id): return user_id"
        assert normalize_latex("post_num = 12345") == "post_num = 12345"
        assert normalize_latex(r"C:\Users\danat\Desktop") == r"C:\Users\danat\Desktop"

    def test_bbcode_integration(self):
        # convert_site_tags_to_telegram should handle both BB-codes and LaTeX
        raw = r"[b]Формула:[/b] \Delta G \lt 0, 10^{11} звезд и 85\% шанса"
        expected = "<b>Формула:</b> ΔG < 0, 10¹¹ звезд и 85% шанса"
        assert convert_site_tags_to_telegram(raw) == expected

    def test_currency_and_file_paths_preserved(self):
        # Currency prices like $50 and $30 must not be stripped as math delimiters
        raw_currency = "Купил видеокарту за $500, продал за $300."
        assert normalize_latex(raw_currency) == raw_currency

        # Windows paths with backslashes like \to, \in must not be converted to symbols
        raw_path = r"Лог сохранен в C:\to\dir\in\file.txt"
        assert normalize_latex(raw_path) == raw_path

        # Snake_case user/post IDs must not have their numbers subscripted
        raw_ids = "Пользователь user_123 ответил на пост_569139 с ID id_42"
        assert normalize_latex(raw_ids) == raw_ids


class TestSplitTextImprovements:
    def test_no_single_word_orphan_chunk(self):
        """Verifies that split_text does not create a tiny trailing chunk for the last word."""
        # Create text just over limit
        p1 = "Первый большой параграф текста. " * 70  # ~2240 chars
        p2 = "Второй большой параграф текста с рассуждениями. " * 60  # ~2820 chars
        full_text = f"{p1}\n\n{p2}"

        parts = split_text(full_text, limit=4000)
        assert len(parts) >= 2
        for idx, part in enumerate(parts):
            assert count_tg_utf16_units(part) <= 4000
            # No part should be just a single word + numbering
            lines = [l for l in part.split('\n') if l.strip() and not l.strip().startswith('(')]
            assert len(lines) > 0
            main_text = " ".join(lines).strip()
            assert len(main_text) > 30, f"Chunk {idx} is unnaturally tiny ({len(main_text)} chars): {part}"

    def test_normalized_post_fits_in_single_message(self):
        """The post from the user's issue must fit in 1 message once LaTeX is normalized."""
        sample_post = (
            r"Эта хуйня, которую ты пытался вспомнить, называется уравнением Дрейка "
            r"(N = R_* \cdot f_p \cdot n_e \cdot f_l \cdot f_i \cdot f_c \cdot L), и последние двадцать лет "
            r"орбитальной спектроскопии от «Кеплера» до «Джеймса Уэбба» превратили его из философской гадалки "
            r"в жесткую воронку статистической отбраковки. В Млечном Пути крутится около 3 \times 10^{11} звезд, "
            r"но 85\% из них сразу летят в мусорное ведро. Ядро и балдж Галактики стерилизованы сверхновыми, "
            r"гамма-всплесками и приливными разрывами, окраины диска бедны тяжелыми элементами (\text{Fe, Si, Mg, P}) "
            r"для сборки нормального каменного ядра, а три четверти всех звезд — это тусклые красные карлики класса М. "
            r"Планета в зоне обитаемости красного карлика заперта в приливном захвате одной стороной к светилу, а сам "
            r"карлик первые полтора миллиарда лет швыряется корональными выбросами массы и жестким рентгеном такой плотности, "
            r"что сдувает океаны и атмосферы до голого базальта через гидродинамическое убегание водорода еще до того, "
            r"как кора успеет остыть.\n"
            r"Если оставить только спокойные оранжевые и желтые карлики (классы K и G) и добавить сюда подледные океаны "
            r"ледяных спутников вокруг газовых гигантов за снеговой линией, мы получаем в нашей Галактике около "
            r"5\text{–}10\text{ миллиардов} объектов, где жидкая вода прямо сейчас контактирует с ультраосновными "
            r"породами мантии. Там, где вода встречается с оливинами и пироксенами, серпентинизация идет со стопроцентной "
            r"термодинамической неизбежностью (\Delta G \lt 0), автоматически штампуя пористые щелочные мембраны из сульфидов "
            r"железа и никеля, водородный поток и естественные протонные градиенты. С учетом термофореза в микропорах, "
            r"который концентрирует органические мономеры в миллионы раз, пробой порога Эйгена и сборка примитивного репликатора — "
            r"это не чудо, а закономерный фазовый переход неравновесной химии, который срабатывает примерно на 1\text{–}5\% "
            r"таких миров. Моя жесткая ставка по факту: прямо сейчас в Млечном Пути функционирует порядка 10^7\text{–}10^8 "
            r"(от десятков до ста миллионов) живых биосфер.\n"
            r"Но прежде чем радоваться этому зоопарку, учти главный термодинамический фильтр: 99.99\% из этих ста миллионов "
            r"живых миров — это тупая, слепая одноклеточная слизь, навсегда застрявшая на уровне архей и хемолитотрофных бактерий. "
            r"Большая их часть запечатана под двадцатикилометровым панцирем льда в аналогах Европы и Энцелада без единого звездного "
            r"фотона, где потолок свободной энергии ограничен метаногенезом и восстановлением сульфатов "
            r"(\Delta G \approx -20\text{…}-40\text{ кДж/моль}), чего физически не хватит даже на прокорм многоклеточного червяка. "
            r"Но даже на открытых планетах под светом звезды переход от бактериального мата к сложной макрофауне требует двух "
            r"статистических уродств, которые на Земле случились всего по одному разу за четыре миллиарда лет: изобретения марганцевого "
            r"кластера \text{Mn}_4\text{CaO}_5 для четырехэлектронного разложения воды и выброса свободного кислорода "
            r"(E^\circ = +0.82\text{ В}), и эндосимбиоза — случайного поглощения археей альфа-протеобактерии с превращением ее в "
            r"митохондрию, что сняло энергетическое проклятие отношения площади мембраны к объему клетки. Добавь сюда геофизическое "
            r"лезвие бритвы: если на каменную планету при формировании выпало чуть больше воды (хотя бы 1\% от массы планеты вместо "
            r"земных 0.02\%), давление на дне океана пробивает 2\text{ ГПа}, вода кристаллизуется в тяжелый горячий лед VI и VII, "
            r"который намертво изолирует мантию от океана, вырубает карбонатно-силикатный термостат, и биосфера задыхается без притока "
            r"минералов и \text{CO}_2. В итоге сложная аэробная многоклеточная жизнь прямо сейчас ползает и плавает от силы на "
            r"10^3\text{–}10^4 (нескольких тысячах) планет на всю Галактику.\n"
            r"А теперь прогоняем эти несколько тысяч миров с животными и лесами через финальную мясорубку технологического перехода. "
            r"Тебе нужны открытые континенты (в чистом планетарном океане ты никогда не выплавишь медь и не соберешь радиолампу в "
            r"соленой воде), узкое окно парциального давления кислорода в атмосфере между 18\% (ниже костер тупо не горит, прощай металлургия) "
            r"и 25\% (выше от одного удара молнии сгорают даже мокрые"
        )
        head = "🔴 <b>/b/</b> | <b>Пост №569139</b>"
        normalized = convert_site_tags_to_telegram(sample_post)
        full = f"{head}\n\n{normalized}"
        assert count_tg_utf16_units(full) <= 4096
        parts = split_text(full, limit=4096)
        assert len(parts) == 1
