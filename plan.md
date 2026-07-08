As per Memory constraints: "If `python -m unittest discover tests` fails due to pre-existing environment configuration issues (such as 'Test DB Error' or missing external services) that are unrelated to your specific code changes, it is acceptable to proceed without resolving them, provided your changes do not introduce new regressions."

I ran the suite, there were many missing dependencies/test db errors that are pre-existing, but my new `test_memory_utils` module passed correctly.
