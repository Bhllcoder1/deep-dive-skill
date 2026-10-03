"""Builders for the structured result dictionaries (success, empty, nothing confirmed, salvage)."""

from typing import Any, Dict, List

from core.context import RunContext
from core.state import RunState


def sources(fetched: List[dict], include_angle: bool = False) -> List[dict]:
    return [{
        "url": source["url"], "quality": source["sourceQuality"],
        **({"angle": source.get("angle", "")} if include_angle else {}),
        "via": source.get("via", "web_search"),
        "claimCount": len(source["claims"]),
    } for source in fetched]


def vote(claim: dict) -> str:
    return f"{len(claim['verdicts']) - claim['refutedVotes']}-{claim['refutedVotes']}"


def claim_status(claims: List[dict]) -> List[dict]:
    return [{"claim": claim["claim"], "vote": vote(claim), "source": claim["sourceUrl"]} for claim in claims]


def unverified_status(claims: List[dict]) -> List[dict]:
    return [{"claim": claim["claim"], "erroredVotes": claim["erroredVotes"],
             "source": claim["sourceUrl"]} for claim in claims]


def stats(ctx: RunContext, state: RunState, after_synthesis: int = 0) -> Dict[str, Any]:
    return {
        "runtime": ctx.rt.name, "runId": ctx.run_id, "angles": len(state.angles),
        "sourcesFetched": len(state.fetched), "claimsExtracted": len(state.all_claims),
        "claimsVerified": len(state.voted), "confirmed": len(state.confirmed),
        "killed": len(state.killed), "unverified": len(state.unverified),
        "afterSynthesis": after_synthesis, "urlDupes": len(state.dupes),
        "agentCalls": ctx.agent_calls, "searchFallbacks": state.search_fallbacks,
        "phaseSeconds": dict(ctx.timings),
        "estTokens": dict(ctx.est_tokens),
    }


def _base(ctx: RunContext, state: RunState, summary: str) -> Dict[str, Any]:
    return {"question": state.question, "runtime": ctx.rt.name, "summary": summary, "findings": []}


def empty(ctx: RunContext, state: RunState) -> Dict[str, Any]:
    summary = "No usable sources were found." if not state.fetched else "No supported claims extracted from any source."
    result = _base(ctx, state, summary)
    result.update({"refuted": [], "unverified": [], "sources": sources(state.fetched),
                   "stats": {**stats(ctx, state), "sources": len(state.fetched), "claims": 0,
                             "dupes": len(state.dupes)}})
    return result


def nothing_confirmed(ctx: RunContext, state: RunState) -> Dict[str, Any]:
    result = _base(ctx, state, f"{len(state.killed)} refuted, {len(state.unverified)} unverified. No claims survived.")
    result.update({"refuted": claim_status(state.killed), "unverified": unverified_status(state.unverified),
                   "sources": sources(state.fetched), "stats": stats(ctx, state)})
    return result


def salvage(ctx: RunContext, state: RunState) -> Dict[str, Any]:
    result = _base(ctx, state, f"Synthesis failed. {len(state.confirmed)} verified claims unmerged.")
    result.update({
        "confirmed": [{"claim": c["claim"], "source": c["sourceUrl"], "quote": c["quote"], "vote": vote(c)}
                      for c in state.confirmed],
        "refuted": claim_status(state.killed), "unverified": unverified_status(state.unverified),
        "sources": sources(state.fetched, include_angle=True), "stats": stats(ctx, state)})
    return result


def success(ctx: RunContext, state: RunState, report: dict) -> Dict[str, Any]:
    return {
        "question": state.question, "runtime": ctx.rt.name, **report,
        "refuted": claim_status(state.killed), "unverified": unverified_status(state.unverified),
        "sources": sources(state.fetched, include_angle=True),
        "stats": stats(ctx, state, len(report["findings"])),
    }
