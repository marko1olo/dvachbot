1. **Modify `main.py` (`_delete_user_posts_from_db`)**
   - Use `json_each` to batch the threads lookup query (`SELECT thread_id FROM Threads WHERE thread_id IN (SELECT value FROM json_each(?)) OR thread_num IN (SELECT value FROM json_each(?))`) instead of chunking over `user_posts`.
   - Use `json_each` to batch the post lookup query (`SELECT post_num FROM Posts WHERE thread_id IN (SELECT value FROM json_each(?))`) instead of chunking over `t_ids`.

2. **Modify `delete_user_posts.py` (`delete_user_posts`)**
   - Use `json_each` to batch the threads lookup query (`SELECT thread_id FROM Threads WHERE thread_id IN (SELECT value FROM json_each(?)) OR thread_num IN (SELECT value FROM json_each(?))`) instead of chunking over `user_posts`.
   - Use `json_each` to batch the post lookup query (`SELECT post_num FROM Posts WHERE thread_id IN (SELECT value FROM json_each(?))`) instead of chunking over `t_ids`.

3. **Verify Syntax and Clean Up**
   - Run `python -m py_compile main.py delete_user_posts.py` via `run_in_bash_session` to ensure no syntax errors are present.
   - Remove temporary files `benchmark.py` and `benchmark2.py` via `run_in_bash_session`.

4. **Verify Functionality**
   - Run the test suite via `run_in_bash_session` with `python -m unittest discover tests`.

5. **Complete Pre-Commit Steps**
   - Complete pre commit steps to ensure proper testing, verification, review, and reflection are done.

6. **Create PR with Performance Improvements**
   - Use `run_in_bash_session` to execute git and GitHub CLI commands: `git checkout -b perf-optimize-n1`, `git add .`, `git commit -m "⚡ Optimize N+1 queries in archive cleanup using json_each"`, `gh pr create --title "⚡ Optimize N+1 Queries in Archive Cleanup" --body "..."`
