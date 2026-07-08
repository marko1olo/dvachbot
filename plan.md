1. **Refactor `graceful_shutdown`**
   - In `main.py`, the function `graceful_shutdown` has a lot of heavy dependencies that are difficult to mock for tests. To test it effectively without running into circular import and complex mocking issues with `sys.modules`, I will extract its core logic into a separate file `common/shutdown.py` as a function `_graceful_shutdown_impl`.
   - `main.py` will keep the `graceful_shutdown` function which will act as a thin wrapper, calling `_graceful_shutdown_impl` with its global variables and imported functions as arguments. This inversion of control will make testing trivial.
2. **Add Tests**
   - Create `tests/test_graceful_shutdown.py` with an isolated async test case for the extracted `_graceful_shutdown_impl` function.
   - The test will cover success, database error, polling error, and the early return when `is_shutting_down` is already true. Mock heavy components such as the DB pool and task executors.
3. **Execute Tests**
   - Run `python -m unittest discover tests` to ensure all tests, including the newly added tests, pass.
4. **Pre-commit Steps**
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.
5. **Submit Change**
   - Create a branch, commit the refactor and new tests, and push via PR with a proper message.
