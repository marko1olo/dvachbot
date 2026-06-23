However, `main.py` is written such that importing it executes tons of code: `dp.callback_query.middleware()` and other stuff. Mocking ALL of `aiogram`'s API surface just so it doesn't crash on import is very hard and brittle.

Look at how `clean_zalgo` is tested.
`from Dubsite_tgach.main import clean_zalgo`
It imports from `Dubsite_tgach.main`!

Is `sanitize_html` in `Dubsite_tgach.main`? Yes, at line 1613, BUT its implementation is different:
```python
def sanitize_html(text: str) -> str:
    if not text:
        return ""
    # quote=False оставляет кавычки как есть (читаемее), но убивает теги
    return html.escape(text, quote=False)
```
Wait! The task specifically points out: "Issue: Untested link formatting helper in clean_html_tags". It refers to the `def sanitize_html` in `main.py` that has `link_replacer`.
Since `main.py` fails on import because of global execution, AST execution of just that function is the safest bet to test it without refactoring the whole module.

Wait! I can also just `patch` everything that runs on import? No, AST is better.

I will just create `tests/test_sanitize_html.py` which uses the AST approach or `exec` to extract `sanitize_html`, and write thorough tests for it.
This provides the testing coverage needed without fighting the spaghetti architecture of `main.py`.

Let's request plan review!
