# Dispatch Assignment — challenger_m1_1

## Identity
- Role: teamwork_preview_challenger (Adversarial Regex & Edge Case Verifier)
- Working Directory: C:\Users\danat\Desktop\dvachbot\.agents\challenger_m1_1
- Target Project Directory: C:\Users\danat\Desktop\dvachbot
- Original Request File: C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md
- Worker Handoff: C:\Users\danat\Desktop\dvachbot\.agents\worker_m1\handoff.md

## Objective — Stress-Test Milestone 1 (M1)
Empirically challenge and stress-test the HTML anchor parsing and regex fixes.

Specifically:
1. Construct adversarial input strings (e.g. malformed URLs, nested quotes `href="https://a.com'b"`, multiple `>>1234` quotes, mixed HTML entities `&quot;`, `&amp;`, `&#039;`, unicode, Russian text immediately following link without space `https://domain.com/path'>Текст`).
2. Run backend `format_post_text` and frontend `formatTextGlobal`/`parseTextEffects` on these adversarial inputs.
3. Verify zero quote/entity leaks, zero unclosed tags, zero nested `<a>` tags.
4. Output your verdict (`APPROVE` or `REJECT`) in `C:\Users\danat\Desktop\dvachbot\.agents\challenger_m1_1\handoff.md`.
