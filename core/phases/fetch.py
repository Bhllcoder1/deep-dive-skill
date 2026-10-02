"""Phase 3 — fetch each source and extract falsifiable claims (parallel), then rank claims."""

from typing import Any, Dict

from core import prompts, results, validate
from core.context import RunContext
from core.schemas import EXTRACT_SCHEMA
from core.state import RunState

NAME = "Fetch"


def _fetch_source(ctx: RunContext, source: Dict[str, str]) -> Dict[str, Any]:
    ctx.log(f"İşleniyor: {source['title'][:60] or source['url'][:60]}")
    content = ctx.web_fetch(source["url"])
    extracted = None
    if content:
        extracted = ctx.agent(prompts.fetch(source, ctx.question, source["angle"], content), EXTRACT_SCHEMA,
                              f"fetch:{(source['title'] or source['url'])[:40]}", "Fetch")
    quality, publish_date, claims = validate.valid_extraction(extracted, source)
    for claim in claims:
        claim["quoteInSource"] = bool(content) and validate.quote_in_source(claim["quote"], content)
    ctx.log(f"  → {len(claims)} claim çıkarıldı" if content and extracted else "  → fetch/extraction başarısız")
    return {"url": source["url"], "title": source["title"], "angle": source["angle"],
            "via": source.get("via", "web_search"), "sourceQuality": quality,
            "publishDate": publish_date, "claims": claims}


def run(ctx: RunContext, state: RunState) -> None:
    ctx.phase("3/5", f"Fetch — {len(state.sources)} kaynaktan claim extraction")
    outputs = ctx.run_parallel([lambda source=source: _fetch_source(ctx, source) for source in state.sources])
    for source, output in zip(state.sources, outputs):
        state.fetched.append(output or {
            "url": source["url"], "title": source["title"], "angle": source["angle"],
            "via": source.get("via", "web_search"), "sourceQuality": "unreliable",
            "publishDate": "", "claims": []})

    state.all_claims = [claim for source in state.fetched for claim in source["claims"]]
    state.all_claims.sort(key=lambda claim: (
        validate.imp_rank(claim["importance"]), validate.qual_rank(claim["sourceQuality"]),
        not claim.get("quoteInSource", False),
    ))
    state.ranked_claims = state.all_claims[:ctx.cfg.max_verify_claims]
    ctx.log(f"{len(state.fetched)} kaynak → {len(state.all_claims)} claim → ilk {len(state.ranked_claims)} doğrulanacak")
    if not state.ranked_claims:
        state.result = results.empty(ctx, state)
