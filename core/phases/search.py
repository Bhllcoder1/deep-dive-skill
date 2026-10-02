"""Phase 2 — one real web search per angle, run in parallel.

The LLM is a fallback only: with no browser its "results" are unverified URLs, so it is
used solely when the search backend returned nothing, and every such case is logged and
counted (``stats.searchFallbacks``, ``sources[].via``).
"""

from typing import Any, Dict, List, Tuple

from core import prompts, validate
from core.context import RunContext
from core.schemas import SEARCH_SCHEMA
from core.state import RunState
from core.urlsafe import normalize_public_url

NAME = "Search"


def _search_angle(ctx: RunContext, angle: Dict[str, str]) -> Tuple[List[Dict[str, str]], str]:
    ctx.log(f"Aranıyor: {angle['label']} ({angle['query'][:60]}...)")
    results = ctx.web_search(angle["query"])
    if results:
        return results, "web_search"
    ctx.log(f"web_search '{angle['label']}' için sonuç vermedi — LLM yedeğine geçiliyor "
            "(fallback; kaynaklar doğrulanmamış olabilir)")
    reply = ctx.agent(prompts.search(angle, ctx.question), SEARCH_SCHEMA, f"search:{angle['label']}", "Search")
    return validate.valid_search_results((reply or {}).get("results")), "llm-fallback"


def run(ctx: RunContext, state: RunState) -> None:
    ctx.phase("2/5", f"Search — {len(state.angles)} paralel web araması")
    outputs = ctx.run_parallel([lambda angle=angle: _search_angle(ctx, angle) for angle in state.angles])

    seen: Dict[str, Dict[str, Any]] = {}
    for angle, output in zip(state.angles, outputs):
        results, via = output if output else ([], "web_search")
        if via == "llm-fallback":
            state.search_fallbacks += 1
        results.sort(key=lambda result: validate.rel_rank(result["relevance"]))
        for result in results:
            key = normalize_public_url(result["url"]) or ""
            if key in seen:
                state.dupes.append({"url": result["url"], "angle": angle["label"], "dupOf": seen[key]})
                continue
            if len(state.sources) >= ctx.cfg.max_fetch:
                continue
            seen[key] = {"angle": angle["label"], "title": result["title"]}
            state.sources.append({**result, "angle": angle["label"], "via": via})

    ctx.log(f"{len(state.sources)} unique kaynak, {len(state.dupes)} dupe, {len(state.sources)} slot kullanıldı")
