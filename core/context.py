"""Per-run services shared by the phases: runtime access, call counting, budgets, timings."""

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core import cache
from core.config import Config
from core.jsonparse import extract_json_object
from core.validate import valid_search_results
from runtime import BaseRuntime


class RunContext:
    """Everything a phase needs. The runtime is only ever touched through here, so
    exceptions are contained, agent calls are counted, and budgets are enforced in one place."""

    def __init__(self, rt: BaseRuntime, cfg: Config, question: str, run_id: Optional[str] = None):
        self.rt = rt
        self.cfg = cfg
        self.question = question
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.timings: Dict[str, float] = {}
        self._calls = 0
        self.est_tokens = {"in": 0, "out": 0}  # rough (chars/4) cost meter for the run
        self._lock = threading.Lock()
        self._phase = ""
        self._phase_start = 0.0
        self._deadline = float("inf")

    # ── counters / timings ──
    @property
    def agent_calls(self) -> int:
        return self._calls

    def begin_phase(self, name: str) -> None:
        self._phase, self._phase_start = name, time.monotonic()
        self._deadline = self._phase_start + self.cfg.phase_budget_s

    def end_phase(self) -> None:
        if self._phase:
            self.timings[self._phase] = round(time.monotonic() - self._phase_start, 3)
        self._phase, self._deadline = "", float("inf")

    def over_budget(self) -> bool:
        return time.monotonic() > self._deadline

    # ── messages ──
    def log(self, message: str) -> None:
        try:
            self.rt.log(message)
        except Exception:
            pass

    def phase(self, label: str, detail: str) -> None:
        try:
            self.rt.phase(label, detail)
        except Exception:
            pass

    # ── runtime boundaries (never raise) ──
    def agent(self, prompt: str, schema: dict, label: str, phase: str) -> Optional[dict]:
        with self._lock:
            self._calls += 1
            self.est_tokens["in"] += len(prompt) // 4
        try:
            raw = self.rt.agent_call(prompt, schema=schema, label=label, phase=phase)
            with self._lock:
                self.est_tokens["out"] += len(raw if isinstance(raw, str) else repr(raw)) // 4
            return extract_json_object(raw)
        except Exception as error:
            self.log(f"{label} başarısız: {type(error).__name__}")
            return None

    def web_search(self, query: str) -> List[Dict[str, str]]:
        cached = cache.get("search", query)
        if cached:
            return valid_search_results(cached)
        try:
            raw = self.rt.web_search(query, max_results=6)
        except Exception as error:
            self.log(f"web_search başarısız ({type(error).__name__})")
            return []
        found = valid_search_results(raw)
        cache.put("search", query, found)
        return found

    def web_fetch(self, url: str) -> Optional[str]:
        cached = cache.get("fetch", url)
        if isinstance(cached, str):
            return cached
        try:
            content = self.rt.web_fetch(url)
        except Exception as error:
            self.log(f"fetch başarısız ({type(error).__name__}): {url[:80]}")
            return None
        text = content.strip()[:15000] or None if isinstance(content, str) else None
        cache.put("fetch", url, text)
        return text

    def run_parallel(self, functions: List[Callable[[], Any]]) -> List[Any]:
        """Run in batches of at most cfg.max_workers (even if the runtime ignores the bound),
        stopping to start new batches once the phase budget is spent. Result order and length
        always match ``functions``; missing/failed entries are None."""
        results: List[Any] = []
        step = self.cfg.max_workers
        for start in range(0, len(functions), step):
            batch = functions[start:start + step]
            if self.over_budget():
                self.log(f"faz bütçesi ({self.cfg.phase_budget_s}s) doldu — {len(functions) - start} iş atlandı")
                results.extend([None] * (len(functions) - start))
                break
            try:
                batch_results = self.rt.run_parallel(batch, max_workers=len(batch))
            except Exception as error:
                self.log(f"paralel batch başarısız: {type(error).__name__}")
                batch_results = []
            if not isinstance(batch_results, list):
                batch_results = []
            results.extend(batch_results[:len(batch)])
            results.extend([None] * max(0, len(batch) - len(batch_results)))
        return results
