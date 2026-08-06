# Master Execution Plan: dvachbot Audit & Repair

## Overview
Comprehensive audit and repair of `dvachbot` codebase addressing broad exception swallowing (`except Exception:`, Telegram API errors like `TelegramForbiddenError` / `TelegramBadRequest`), asynchronous queue integrity (`delivery_manager.py`, `broadcaster.py`, `post_processor.py`), and static verification (`py_compile`).

## Milestones

### Phase 1: Exploration & Survey
- [ ] Explorer 1: Broad Exception & Telegram API Exception Scan (`periodic_publisher.py`, `broadcaster.py`, `user_manager.py`, etc.)
- [ ] Explorer 2: Asynchronous Queue & Task Loop Integrity Audit (`delivery_manager.py`, `broadcaster.py`, `post_processor.py`, etc.)
- [ ] Explorer 3: Codebase Topology & Dependency Analysis (Aiogram 3 best practices, error hierarchy, logging consistency)

### Phase 2: Implementation (Milestones M1 & M2)
- [ ] M1: Broad Exception Auditing & Telegram API Error Hardening
  - Catch explicit Telegram errors (`TelegramForbiddenError`, `TelegramBadRequest`, `TelegramAPIError`).
  - Update user state on block/deactivation where applicable (`TelegramForbiddenError`).
  - Log unhandled errors with tracebacks/context instead of silent suppression.
- [ ] M2: Asynchronous Queue Integrity & Loop Resilience
  - Protect worker loops and broadcast queues from crashing on single item failure.
  - Implement task error isolation, retry/dlq logic or safe item drop with explicit logging.
  - Ensure queues (`delivery_manager.py`, `broadcaster.py`, `post_processor.py`) handle exceptions per-item without stopping or dropping pending items.

### Phase 3: Review, Hardening & Forensic Audit (Milestone M3)
- [ ] Code Reviewers: Reviewer 1 & Reviewer 2 check code quality, Aiogram 3 compliance, error handling precision.
- [ ] Adversarial Challengers: Challenger 1 & Challenger 2 test queue edge cases, synthetic API exception paths, static analysis (`python -m py_compile`).
- [ ] Forensic Auditor: Integrity check ensuring no dummy implementations, fake mocks, or suppressed error paths.
