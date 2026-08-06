## 2026-08-06T23:50:04Z
<USER_REQUEST>
You are Worker 3 (Compilation & AST Remediation Worker). Your working directory is C:\Users\danat\Desktop\dvachbot\.agents\worker_compilation_fix.

MUST read C:\Users\danat\Desktop\dvachbot\.agents\ORIGINAL_REQUEST.md before starting.

Your task: Fix the workspace compilation issue and clean up residual bare `except:` blocks reported by Challenger 1.

Specifically:
1. `main_4days_ago.py` is an obsolete backup file in root directory C:\Users\danat\Desktop\dvachbot. Fix its encoding to UTF-8 or remove/rename it so that `python -c "import compileall; compileall.compile_dir('.', maxlevels=5, quiet=1)"` returns `True` (Exit Code 0 with zero compilation errors across the workspace).
2. Clean up any remaining bare `except:` handlers in `admin_manager.py`, `handlers/message_router.py`, `site_tgach/importer.py`, `site_tgach/mirror_worker.py`, `site_tgach/main.py`, `Dubsite_tgach/main.py`, and `main.py` by replacing untyped `except:` with explicit typed exceptions (e.g. `except Exception:` or specific exception tuples).
3. Run `python -c "import compileall; compileall.compile_dir('.', maxlevels=5, quiet=1)"` to verify that it returns `True`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine.

Output requirements:
- Maintain progress.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_compilation_fix\progress.md.
- Write handoff.md in C:\Users\danat\Desktop\dvachbot\.agents\worker_compilation_fix\handoff.md detailing all changes made.
- Send a message to orchestrator with summary and handoff path.
</USER_REQUEST>
