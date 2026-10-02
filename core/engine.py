"""
Deep Research Engine — Scope → Search → Fetch → Verify → Synthesize.

``run()`` is only the orchestrator: it validates input, prepares the runtime and a
``RunContext``, then runs ``PHASES`` in order until one sets ``state.result``.
Settings come from an explicit ``Config`` (default: ``Config.from_env()``); there is no
module-level state, so concurrent runs with different settings are safe.
"""

from typing import Any, Optional

from core.config import Config
from core.context import RunContext
from core.phases import fetch, scope, search, synthesize, verify
from core.state import RunState
from runtime import BaseRuntime, get_runtime

PHASES = (scope, search, fetch, verify, synthesize)


def run(question: str, runtime: Optional[BaseRuntime] = None, dashboard: Optional[Any] = None,
        config: Optional[Config] = None) -> dict:
    """Run the full deep-research pipeline and return a structured report."""
    if not isinstance(question, str) or not question.strip():
        return {"error": "No research question provided."}
    question = question.strip()

    try:
        rt = runtime or get_runtime()
        if not rt.setup():
            return {"error": f"Runtime '{rt.name}' hazır değil. API key kontrol edin."}
    except Exception:
        return {"error": "Could not initialize the research runtime.", "question": question}

    ctx = RunContext(rt, config or Config.from_env(), question)
    state = RunState(question)
    for phase in PHASES:
        if dashboard:
            try:
                dashboard.select_phase(phase.NAME)
            except Exception:
                pass
        ctx.begin_phase(phase.NAME)
        try:
            phase.run(ctx, state)
        finally:
            ctx.end_phase()
        if state.result is not None:
            return state.result
    return state.result or {"error": "Pipeline produced no result.", "question": question}

