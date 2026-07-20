"""
pipeline() and parallel() — Universal parallel execution.
Mimics Claude Code's pipeline(array, fn) and parallel(fnArray) APIs.

pipeline(items, fn):
    Sequentially maps fn over each item, collecting results.

parallel(fnArray):
    Executes all functions concurrently, returns results in order.
    Falls back to sequential if no parallel runtime available.

Usage:
    results = pipeline(my_array, lambda item: agent(prompt(item)))
    results = parallel([lambda: agent(a), lambda: agent(b)])
"""

import os
import sys
import threading
from typing import Any, Callable, List


def _detect_capability() -> str:
    """Detect parallel execution capability."""
    if os.environ.get("HERMES_AGENT"):
        return "hermes"  # delegate_task for true parallelism
    if os.environ.get("CLAUDE_CODE"):
        return "claude"  # Claude's built-in parallel()
    return "threading"  # Python threading as fallback


def pipeline(items: List[Any], fn: Callable[[Any], Any]) -> List[Any]:
    """
    Sequentially map fn over each item.
    Like JavaScript's Array.map() but with progress logging.

    Args:
        items: List of input items
        fn: Function that transforms an item

    Returns:
        List of results (None results are included, filter with .filter(Boolean))
    """
    results = []
    total = len(items)
    for i, item in enumerate(items):
        print(f"  pipeline: {i+1}/{total}", file=sys.stderr)
        try:
            result = fn(item)
            results.append(result)
        except Exception as e:
            print(f"  pipeline error on item {i}: {e}", file=sys.stderr)
            results.append(None)
    return results


def parallel(fn_list: List[Callable[[], Any]], max_workers: int = 5) -> List[Any]:
    """
    Execute functions concurrently.

    Args:
        fn_list: List of zero-argument callables
        max_workers: Max concurrent threads (default: 5)

    Returns:
        List of results in the same order as fn_list
    """
    capability = _detect_capability()

    if capability == "claude":
        # Inside Claude Code, the JS wrapper intercepts parallel() calls
        print("__CLAUDE_PARALLEL__:" + str(len(fn_list)), file=sys.stderr)
        # Fall through to threading for actual execution
        return _threaded_parallel(fn_list, max_workers)

    if capability == "hermes":
        # Hermes: first try using concurrent subagents
        # But for simple CPU-bound work, threading is fine
        pass

    return _threaded_parallel(fn_list, max_workers)


def _threaded_parallel(fn_list: List[Callable[[], Any]], max_workers: int = 5) -> List[Any]:
    """Execute functions in a thread pool."""
    results = [None] * len(fn_list)
    errors = [None] * len(fn_list)
    lock = threading.Lock()

    def worker(idx: int, fn: Callable):
        try:
            result = fn()
            with lock:
                results[idx] = result
        except Exception as e:
            with lock:
                errors[idx] = e

    threads = []
    total = len(fn_list)

    for i, fn in enumerate(fn_list):
        t = threading.Thread(target=worker, args=(i, fn), daemon=True)
        threads.append(t)
        t.start()

        # Simple throttling: wait if we hit max_workers
        if len([t for t in threads if t.is_alive()]) >= max_workers:
            # Join one to free a slot
            for t in threads:
                if t.is_alive():
                    t.join(timeout=0.1)
                    break

    for t in threads:
        t.join()

    # Log errors
    for i, err in enumerate(errors):
        if err:
            print(f"  parallel worker {i} error: {err}", file=sys.stderr)

    return results
