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
import traceback
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, List, Optional


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
    if not callable(fn):
        raise TypeError("fn must be callable")

    results = []
    total = len(items)
    for i, item in enumerate(items):
        print(f"  pipeline: {i+1}/{total}", file=sys.stderr)
        try:
            result = fn(item)
            results.append(result)
        except Exception as exc:
            _log_failure("pipeline", i, exc)
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
    _validate_max_workers(max_workers)
    functions = list(fn_list)
    for i, fn in enumerate(functions):
        if not callable(fn):
            raise TypeError(f"fn_list[{i}] must be callable")

    capability = _detect_capability()

    if capability == "claude":
        # Inside Claude Code, the JS wrapper intercepts parallel() calls
        print("__CLAUDE_PARALLEL__:" + str(len(functions)), file=sys.stderr)
        # Fall through to threading for actual execution
        return _threaded_parallel(functions, max_workers)

    if capability == "hermes":
        # Hermes: first try using concurrent subagents
        # But for simple CPU-bound work, threading is fine
        pass

    return _threaded_parallel(functions, max_workers)


def run_bounded(fn_list: List[Callable[[], Any]], max_workers: int = 5,
                timeout: Optional[float] = None,
                on_error: Optional[Callable[[int, BaseException], None]] = None,
                on_timeout: Optional[Callable[[int], None]] = None) -> List[Any]:
    """The one bounded-parallel primitive used by every runtime.

    Results keep input order. A failing task yields None (reported via ``on_error``,
    default: traceback on stderr) and never affects its siblings. If ``timeout``
    (seconds, for the whole batch) elapses, unfinished tasks yield None and
    ``on_timeout(count)`` is called; queued tasks are cancelled, tasks already
    running finish on their own (each runtime call carries its own I/O timeout).
    """
    functions = list(fn_list)
    if not functions:
        return []

    results: List[Any] = [None] * len(functions)
    executor = ThreadPoolExecutor(max_workers=min(max_workers, len(functions)),
                                  thread_name_prefix="deep-dive")
    try:
        futures = [executor.submit(fn) for fn in functions]
        _, pending = wait(futures, timeout=timeout)
        for index, future in enumerate(futures):
            if future in pending:
                continue
            try:
                results[index] = future.result()
            except BaseException as exc:  # a worker must not take down its siblings
                (on_error or _log_failure_at)(index, exc)
        if pending and on_timeout is not None:
            on_timeout(len(pending))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _threaded_parallel(fn_list: List[Callable[[], Any]], max_workers: int = 5) -> List[Any]:
    """Execute functions with a bounded pool, keeping input order."""
    return run_bounded(fn_list, max_workers)


def _log_failure_at(index: int, exc: BaseException) -> None:
    _log_failure("parallel worker", index, exc)


def _validate_max_workers(max_workers: int) -> None:
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
        raise ValueError("max_workers must be a positive integer")


def _log_failure(operation: str, index: int, exc: BaseException) -> None:
    """Report an isolated task failure without interrupting sibling tasks."""
    print(f"  {operation} {index} error: {type(exc).__name__}: {exc}", file=sys.stderr)
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
