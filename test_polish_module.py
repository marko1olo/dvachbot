import sys
import unittest.mock

sys.modules['mode_visuals'] = unittest.mock.MagicMock()

import polish_mode

text = "Хороший и красивый день, чтобы выпить пиво!"
print(f"Original: {text}")
result = polish_mode.polish_transform(text)
print(f"Polonized: {result[1]}")

text_adj = "Большой и красный стол."
print(f"Original: {text_adj}")
result_adj = polish_mode.polish_transform(text_adj)
print(f"Polonized: {result_adj[1]}")
