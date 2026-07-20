"""Shared bounded parallel execution for local CLI runtime calls."""

from typing import Any, Callable, List

from core.parallel import _threaded_parallel, _validate_max_workers


def run_cli_parallel(fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
    """Run CLI-invoking callables concurrently while preserving order and failures."""
    if not isinstance(fn_list, (list, tuple)):
        raise TypeError("fn_list must be a list or tuple of callables")
    _validate_max_workers(max_workers)
    functions = list(fn_list)
    for index, fn in enumerate(functions):
        if not callable(fn):
            raise TypeError(f"fn_list[{index}] must be callable")
    return _threaded_parallel(functions, max_workers)
