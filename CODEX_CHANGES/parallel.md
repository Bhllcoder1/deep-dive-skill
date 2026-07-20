# `core/parallel.py`

- Replaced the hand-rolled, racy thread throttle with `ThreadPoolExecutor`, which enforces `max_workers` and waits for all submitted work safely.
- Kept ordered results and `None` placeholders, but now logs each failed worker with its exception type and traceback while allowing other workers to finish.
- Validates `max_workers` and all callables before scheduling any work; `pipeline()` now also rejects a non-callable mapper clearly.
