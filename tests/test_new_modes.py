import unittest
import os
import sys

# Ensure import paths work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from new_modes import (
    matrix_transform,
    rus_transform,
    abu_transform,
    oldweb_transform,
    jewish_transform,
    america_transform,
    holiday_transform,
    transform_america,
    transform_holiday,
)

class TestNewModes(unittest.TestCase):
    def test_matrix_transform(self):
        mode, text = matrix_transform("hello world test text")
        self.assertEqual(mode, "text")
        matrix_keywords = ["MATRIX", "МАТРИЦ", "ZION", "OPERATOR", "KERNEL", "CONSTRUCT", "AGENT", "ENCRYPT", "DECRYPT", "PAYLOAD"]
        self.assertTrue(any(k in text.upper() for k in matrix_keywords))

    def test_rus_transform(self):
        mode, text = rus_transform("я пошел пить воду")
        self.assertEqual(mode, "text")
        rus_keywords = ["БАЙКАЛ", "РУС", "ПЕРУН", "ЯЩЕР", "ВЕЧЕ", "СЛАВЯН"]
        self.assertTrue(any(k in text.upper() for k in rus_keywords))

    def test_rus_all_generators(self):
        import rus_engine
        p = "русичи идут на сечу"
        cm = rus_engine._RUS_COMBAT_MOVES[0]
        rune = rus_engine._RUS_SLAVIC_RUNES[0]

        # 1. Bagirov
        t1 = rus_engine.generate_bagirov_lecture(p, cm, 99)
        self.assertIn("БАГИРОВ", t1)
        self.assertIn("МГУ", t1)

        # 2. Drocheslav
        t2 = rus_engine.generate_drocheslav_raid(p, cm)
        self.assertIn("ДРОЧЕСЛАВ", t2)

        # 3. Wiretap
        t3 = rus_engine.generate_lizard_wiretap(p, cm)
        self.assertIn("ПЕРЕХВАТ ШИФРОВКИ", t3)

        # 4. Court
        t4 = rus_engine.generate_slavic_court(p, rune)
        self.assertIn("НОВГОРОДСКОГО ВЕЧЕ", t4)

        # 5. DNA Test
        t5 = rus_engine.generate_dna_lizard_test(p, 95)
        self.assertIn("ЧИСТОТУ СЛАВЯНСКОЙ КРОВИ", t5)

        # 6. Bugurt
        t6 = rus_engine.generate_slavic_bugurt(p)
        self.assertIn("@", t6)
        self.assertIn("БУГУРТ", t6)

        # 7. Volkhv remedy
        t7 = rus_engine.generate_volkhv_remedy(p, cm)
        self.assertIn("ВСЕСЛАВ", t7)

        # 8. Combat dispatch
        t8 = rus_engine.generate_combat_dispatch(p, cm)
        self.assertIn("РАТНАЯ СВОДКА", t8)

        # 9. Interrogation
        t9 = rus_engine.generate_interrogation_protocol(p, cm, 99)
        self.assertIn("ДОПРОСА ЧЕШУЙЧАТОГО", t9)

        # 10. Whining
        t10 = rus_engine.generate_whining_rebuke(p, cm, 99)
        self.assertIn("ТОСКА", t10)

        # 11. Slavic Horoscope
        t11 = rus_engine.generate_slavic_horoscope(p, rune)
        self.assertIn("СЛАВЯНО-АРИЙСКИЙ ЗВЕЗДОЧЕТ", t11)
        self.assertIn("ЧЕРТОГ", t11)

        # 12. Trade Pact
        t12 = rus_engine.generate_slavic_trade_pact(p, 95)
        self.assertIn("ТОРГОВАЯ ГРАМОТА", t12)
        self.assertIn("КУПЕЧЕСТВ", t12)

        # 13. Hyperborean Chronicle
        t13 = rus_engine.generate_hyperborean_chronicle(p, cm)
        self.assertIn("ГИПЕРБОРЕИ", t13)

        # 14. Slavic Feast Protocol
        t14 = rus_engine.generate_slavic_feast_protocol(p, cm)
        self.assertIn("КНЯЖЕСКОГО ПИРА", t14)

        # 15. Slavic Curse Formula
        t15 = rus_engine.generate_slavic_curse_formula(p, rune)
        self.assertIn("ЗАКЛЯТИЕ", t15)

    def test_rus_interactive_helpers(self):
        import rus_engine
        h1 = rus_engine.generate_rus_horoscope("юзер")
        self.assertIn("ЗВЕЗДОЧЕТ", h1)
        h2 = rus_engine.generate_rus_trade("сделка")
        self.assertIn("ГРАМОТА", h2)
        h3 = rus_engine.generate_rus_hyperborea("космос")
        self.assertIn("ГИПЕРБОРЕ", h3)
        h4 = rus_engine.generate_rus_feast("пир")
        self.assertIn("ПИР", h4)
        h5 = rus_engine.generate_rus_curse("враг")
        self.assertIn("ЗАКЛЯТИЕ", h5)
        h6 = rus_engine.generate_rus_lecture("наука")
        self.assertIn("БАГИРОВ", h6)
        h7 = rus_engine.generate_rus_raid("поход")
        self.assertIn("ДРОЧЕСЛАВ", h7)
        h8 = rus_engine.generate_rus_dna("тест")
        self.assertIn("КРОВ", h8)
        h9 = rus_engine.generate_rus_court("вече")
        self.assertIn("ВЕЧЕ", h9)

    def test_abu_transform(self):
        mode, text = abu_transform("привет двач. как дела?")
        self.assertEqual(mode, "text")
        abu_keywords = ["АБУ", "2CH", "ДВАЧ", "СОСАЧ", "ПАРАШИ", "ДУРКА", "ПСИХИАТРИИ", "ДЕАНОН", "ПАССКОД", "СЫЧ", "БОРД", "СЕРВЕР", "КАПЧ", "ТРЕД", "МАКАК"]
        self.assertTrue(any(k in text.upper() for k in abu_keywords))

    def test_oldweb_transform(self):
        mode, text = oldweb_transform("автор привет медведь круто")
        self.assertEqual(mode, "text")
        self.assertTrue(any(m in text.upper() for m in ["УПЯЧК", "LIVEINTERNET", "QIP", "WINAMP", "ICQ", "ОНОТОЛЕ", "БАШОРГ"]))
        self.assertTrue("аффтар" in text.lower() or "превед" in text.lower() or "медвед" in text.lower())

    def test_jewish_transform(self):
        mode, text = jewish_transform("почем рыба на привозе")
        self.assertEqual(mode, "text")
        jewish_keywords = ["ДЕРИБАСОВСКАЯ", "БАЛКОВСКОЙ", "ТАЛМУД", "ШЕКЕЛ", "РЕБЕ", "ПРИВОЗ", "ЦИЛЯ", "ШАББАТ", "СИНАГОГ"]
        self.assertTrue(any(k in text.upper() for k in jewish_keywords))

    def test_america_transform(self):
        mode, text = america_transform("i want my money back")
        self.assertEqual(mode, "text")
        america_keywords = ["WALL STREET", "DISTRICT COURT", "TEXAS", "CAPITAL", "FREEDOM", "NASDAQ", "CIA", "UNITED STATES"]
        self.assertTrue(any(k in text.upper() for k in america_keywords))

    def test_holiday_transform(self):
        mode, text = holiday_transform("с новым годом аноны")
        self.assertEqual(mode, "text")
        self.assertIn("НОВОГОДН", text.upper())

    def test_aliases(self):
        self.assertIs(america_transform, transform_america)
        self.assertIs(holiday_transform, transform_holiday)

if __name__ == '__main__':
    unittest.main()

