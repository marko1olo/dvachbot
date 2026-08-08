## 2026-08-08T18:44:25Z
Task Instructions for worker_1:
1. Read ORIGINAL_REQUEST.md completely.
2. Read handoffs from explorer_1, explorer_2, explorer_3.
3. Apply fixes in common/database.py and backfill_pf.py:
   - Add single-column indices: CREATE INDEX IF NOT EXISTS idx_postfiles_orig ON PostFiles(original_file_id); and CREATE INDEX IF NOT EXISTS idx_postfiles_thumb ON PostFiles(thumbnail_file_id);
   - Update/refactor legacy functions in common/database.py (find_post_by_file_id, apply_file_action_by_hash, etc.) executing WHERE instr(content, ?) > 0 on Posts to use PostFiles mapping.
4. Ensure PostFiles tag-search mapping is preserved. Run bench_tags.py to confirm tag search is ~30-50ms or faster.
5. Create bench_passive_slice.py to measure passive_slice execution time < 3.0s.
6. Verify dvachbot starts up cleanly without crashes.
7. Create handoff.md and changes.md in .agents/worker_1.
8. Send completion report to parent via send_message.
