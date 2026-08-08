# Dispatch Assignment — worker_m1_gen2

## Identity
- Role: teamwork_preview_worker (HTML Anchor & Regex Fix Specialist — Iteration 2)
- Working Directory: C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_gen2
- Target Project Directory: C:\Users\danat\Desktop\dvachbot
- Original Request File: C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md
- Scope Document: C:\Users\danat\Desktop\dvachbot\.agents\orchestrator\PROJECT.md
- Reviewer Failure Report: C:\Users\danat\Desktop\dvachbot\.agents\reviewer_m1_1\handoff.md

## Objective — Fix Milestone 1 (M1) Regression
Fix the regression identified by `reviewer_m1_1` where multi-parameter URLs containing `&` or query parameters (e.g. `https://example.com/search?q=1&lang=en` or YouTube `watch?v=123&t=30s`) were truncated by the regex `[^\s<>"'\s&#;]+`.

Specifically:
1. **Fix `URL_PATTERN` (Backend) & `linkRegex` (Frontend)**:
   - Do NOT exclude `&` or `;` from URL body matching. URLs MUST support ampersands and query parameters (`?q=1&lang=en`, `?v=abc&t=10s`).
   - Cleanly handle trailing HTML entities (e.g., `&#039;`, `&#x27;`, `&gt;`, `&lt;`, `&quot;`, trailing punctuation) that get appended after quotes/delimiters (e.g., `https://domain.com/b/res/343717.html'>ТГАЧ`).
   - Strategy: Match the URL candidate (allowing query params & entities), then strip trailing HTML entities (`&#039;`, `&#x27;`, `&gt;`, etc.) from the end of the URL before inserting into `<a href="...">`.
2. **Prevent Double-Parsing & Nested Anchors**:
   - Preserve the nested anchor prevention regex replacer in `parseTextEffects`: `/(<a\b[^>]*>[\s\S]*?<\/a>)|(?<!["'=])(...)/gi`.
3. **Synchronize Frontend Files**:
   - Apply JS edits identically to both `site_tgach/static/js/main.src.js` AND `site_tgach/static/js/main.js`.
4. **Mandatory Comprehensive Unit Tests**:
   - Update `tests/test_html_anchors.py` and `tests/test_html_anchors_frontend.js` to explicitly test BOTH:
     a) `https://domain.com/b/res/343717.html'>ТГАЧ` -> `href="https://domain.com/b/res/343717.html"`
     b) `https://example.com/search?q=1&lang=en` -> `href` MUST contain `q=1` AND `lang=en`.
     c) YouTube links `https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s` -> `href` MUST contain `t=30s`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Output Requirements
Write your handoff report to C:\Users\danat\Desktop\dvachbot\.agents\worker_m1_gen2\handoff.md including passing build and test outputs for both simple and multi-parameter query URLs.
