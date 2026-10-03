"""Phase 2 — one real web search per angle, run in parallel.

The LLM is a fallback only: with no browser its "results" are unverified URLs, so it is
used solely when the search backend returned nothing, and every such case is logged and
counted (``stats.searchFallbacks``, ``sources[].via``).
"""

from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit

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

    # Round-robin over the angles (best result of each first) so one angle cannot take every
    # slot, and cap pages per site so one outlet cannot dominate the evidence.
    queues: List[Tuple[Dict[str, str], List[Dict[str, str]], str]] = []
    for angle, output in zip(state.angles, outputs):
        results, via = output if output else ([], "web_search")
        if via == "llm-fallback":
            state.search_fallbacks += 1
        queues.append((angle, sorted(results, key=lambda result: validate.rel_rank(result["relevance"])), via))

    seen: Dict[str, Dict[str, Any]] = {}
    per_site: Dict[str, int] = {}
    for rank in range(max((len(q[1]) for q in queues), default=0)):
        for angle, results, via in queues:
            if rank >= len(results):
                continue
            result = results[rank]
            key = normalize_public_url(result["url"]) or ""
            if key in seen:
                state.dupes.append({"url": result["url"], "angle": angle["label"], "dupOf": seen[key]})
                continue
            site = (urlsplit(key).hostname or "").removeprefix("www.")
            if len(state.sources) >= ctx.cfg.max_fetch or per_site.get(site, 0) >= ctx.cfg.max_per_domain:
                continue
            seen[key] = {"angle": angle["label"], "title": result["title"]}
            per_site[site] = per_site.get(site, 0) + 1
            state.sources.append({**result, "angle": angle["label"], "via": via})

    ctx.log(f"{len(state.sources)} unique kaynak, {len(state.dupes)} dupe, {len(state.sources)} slot kullanıldı")
