import unittest
import io
from PIL import Image
from combat_visuals import draw_duel_poster, draw_rob_poster

class TestCombatVisuals(unittest.TestCase):
    def test_draw_duel_poster(self):
        buf = draw_duel_poster(winner_id=1234, loser_id=5678, amount=250, board_id="b", winner_prefix="Олигарх")
        self.assertIsInstance(buf, io.BytesIO)
        img = Image.open(buf)
        self.assertEqual(img.size, (960, 540))

    def test_draw_rob_poster_success(self):
        buf = draw_rob_poster(robber_id=1111, victim_id=2222, amount=150, outcome="success", board_id="b")
        self.assertIsInstance(buf, io.BytesIO)
        img = Image.open(buf)
        self.assertEqual(img.size, (960, 540))

    def test_draw_rob_poster_tinfoil(self):
        buf = draw_rob_poster(robber_id=1111, victim_id=2222, amount=150, outcome="tinfoil", board_id="b")
        self.assertIsInstance(buf, io.BytesIO)
        img = Image.open(buf)
        self.assertEqual(img.size, (960, 540))

if __name__ == '__main__':
    unittest.main()
