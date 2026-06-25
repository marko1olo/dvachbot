🧪 [testing improvement] Add tests for html_utils.escape_html

🎯 **What:** Added tests to cover the functionality of `escape_html` function in `common/html_utils.py` that was missing testing.

📊 **Coverage:**
- Empty string and `None` value inputs.
- Safe strings (no HTML entities to escape).
- Strings containing `&`.
- Strings containing `<` and `>`.
- Strings containing quotes `"`.
- Combined strings containing multiple entities that should be escaped.

✨ **Result:** Test coverage for `html_utils.escape_html` is complete. The test suite correctly validates proper character encoding for safe usage in HTML, reducing risks of future regressions during refactoring.
