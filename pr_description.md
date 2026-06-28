🎯 **What:** The testing gap in `new_modes.py` was addressed by adding a dedicated test file `tests/test_new_modes.py` to cover the previously untested `_match_case` string formatting function.

📊 **Coverage:** The following scenarios of `_match_case` are now tested:
- Branch 1: Handling an empty source string by returning the replacement exactly as provided.
- Branch 2: Handling fully uppercase source strings (including 1-character uppercase strings) by returning an uppercase replacement string.
- Branch 3: Handling title-case source strings (first letter uppercase, rest lowercase) by returning the replacement string with the first letter capitalized.
- Branch 4: Handling standard lowercase or mixed-case string structures appropriately by returning the replacement exactly as provided.

✨ **Result:** Increased unit test coverage and confidence around the text matching algorithm used in `new_modes.py`.
