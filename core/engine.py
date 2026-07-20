"""
Deep Research Engine — Universal Pipeline.
Runtime'dan bağımsız: Scope → Search → Fetch → Verify → Synthesize.
Her platform kendi runtime adaptörü ile aynı pipeline'ı çalıştırır.
"""

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from runtime import get_runtime, BaseRuntime
from core.tiers import resolve_tier, HARD_MAX_WORKERS

# ─── Configuration ───
# DR_COST_TIER (low/medium/high/ultra) sets the whole preset; any of the
# DR_* vars below can still override a single knob explicitly.
_TIER = resolve_tier(os.environ.get("DR_COST_TIER", ""))


def _cfg_int(env_key: str, tier_key: str) -> int:
    if env_key in os.environ:
        return int(os.environ[env_key])
    return _TIER[tier_key]


ANGLES = _cfg_int("DR_ANGLES", "angles")
VOTES_PER_CLAIM = _cfg_int("DR_VOTES_PER_CLAIM", "votes_per_claim")
REFUTATIONS_REQUIRED = _cfg_int("DR_REFUTATIONS_REQUIRED", "refutations_required")
MAX_FETCH = _cfg_int("DR_MAX_FETCH", "max_fetch")
MAX_VERIFY_CLAIMS = _cfg_int("DR_MAX_VERIFY_CLAIMS", "max_verify_claims")
# Hard-capped regardless of tier/override — the actual "no agent spam" ceiling.
MAX_WORKERS = min(_cfg_int("DR_MAX_WORKERS", "max_workers"), HARD_MAX_WORKERS)


def run(question: str, runtime: Optional[BaseRuntime] = None,
        dashboard: Optional[Any] = None) -> dict:
    """
    Run the full deep research pipeline.

    Args:
        question: Research question
        runtime: Runtime adaptörü (None = otomatik algıla)

    Returns:
        Structured research report dict
    """
    if not question or not question.strip():
        return {"error": "No research question provided."}

    # Runtime hazırla
    rt = runtime or get_runtime()
    if not rt.setup():
        return {"error": f"Runtime '{rt.name}' hazır değil. API key kontrol edin."}
    
    # Dashboard phase'leri güncelle
    if dashboard:
        dashboard.select_phase("Scope")

    rt.phase("1/5", f"Scope — soruyu {ANGLES} search angle'a böl: {question[:80]}...")

    # ─── Phase 1: Scope ───
    scope = rt.agent_call(
        _scope_prompt(question),
        label="scope",
        phase="Scope",
    )
    if not scope:
        return {"error": "Scope agent returned no result.", "question": question}

    angles = scope.get("angles", [])
    if not angles:
        return {"error": "No angles generated from scope.", "question": question}

    rt.log(f"Soru {len(angles)} angle'a bölündü: {', '.join(a['label'] for a in angles)}")

    # ─── Phase 2: Search ───
    rt.phase("2/5", f"Search — {len(angles)} paralel web araması")
    seen_urls = {}
    all_sources = []
    dupes = []
    fetch_slots = MAX_FETCH

    for angle in angles:
        rt.log(f"Aranıyor: {angle['label']} ({angle['query'][:60]}...)")
        search_result = rt.agent_call(
            _search_prompt(angle, question),
            label=f"search:{angle['label']}",
            phase="Search",
        )
        if not search_result:
            continue

        results = search_result.get("results", [])
        results.sort(key=lambda r: _rel_rank(r.get("relevance", "low")))

        for r in results:
            key = _norm_url(r.get("url", ""))
            if not key:
                continue
            if key in seen_urls:
                dupes.append({"url": r["url"], "angle": angle["label"], "dupOf": seen_urls[key]})
                continue
            if fetch_slots <= 0 and _rel_rank(r.get("relevance", "low")) >= 1:
                continue

            seen_urls[key] = {"angle": angle["label"], "title": r.get("title", "")}
            fetch_slots -= 1
            all_sources.append({
                "url": r["url"],
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "relevance": r.get("relevance", "medium"),
                "angle": angle["label"],
            })

    rt.log(f"{len(all_sources)} unique kaynak, {len(dupes)} dupe, {MAX_FETCH - fetch_slots} slot kullanıldı")

    # ─── Phase 3: Fetch ───
    rt.phase("3/5", f"Fetch — {len(all_sources)} kaynaktan claim extraction")
    fetched_sources = []

    for source in all_sources:
        rt.log(f"İşleniyor: {source.get('title', source['url'])[:60]}")
        content = rt.web_fetch(source["url"])

        if content:
            extract_result = rt.agent_call(
                _fetch_prompt(source, question, source["angle"]),
                label=f"fetch:{source.get('title', source['url'])[:40]}",
                phase="Fetch",
            )
            if extract_result:
                claims = extract_result.get("claims", [])
                for c in claims:
                    c["sourceUrl"] = source["url"]
                    c["sourceQuality"] = extract_result.get("sourceQuality", "unreliable")
                    c["angle"] = source["angle"]

                fetched_sources.append({
                    "url": source["url"],
                    "title": source.get("title", ""),
                    "angle": source["angle"],
                    "sourceQuality": extract_result.get("sourceQuality", "unreliable"),
                    "publishDate": extract_result.get("publishDate", ""),
                    "claims": claims,
                })
                rt.log(f"  → {len(claims)} claim çıkarıldı")
                continue

        fetched_sources.append({
            "url": source["url"],
            "title": source.get("title", ""),
            "angle": source["angle"],
            "sourceQuality": "unreliable",
            "claims": [],
        })
        rt.log(f"  → fetch başarısız")

    # Collect and rank all claims
    all_claims = []
    for s in fetched_sources:
        all_claims.extend(s.get("claims", []))

    all_claims.sort(key=lambda c: (_imp_rank(c.get("importance", "tangential")),
                                    _qual_rank(c.get("sourceQuality", "unreliable"))))
    ranked_claims = all_claims[:MAX_VERIFY_CLAIMS]

    rt.log(f"{len(fetched_sources)} kaynak → {len(all_claims)} claim → ilk {len(ranked_claims)} doğrulanacak")

    if not ranked_claims:
        return _empty_result(question, angles, fetched_sources, all_claims, dupes)

    # ─── Phase 4: Verify ───
    rt.phase("4/5", f"Verify — {len(ranked_claims)} claim, {VOTES_PER_CLAIM}-vote adversarial verification")

    # Paralel verify — her claim için VOTES_PER_CLAIM verifier
    verify_fns = []
    verify_specs = []

    for claim in ranked_claims:
        for v in range(VOTES_PER_CLAIM):
            spec = (claim, v)
            verify_specs.append(spec)
            verify_fns.append(lambda s=spec: rt.agent_call(
                _verify_prompt(s[0], question, s[1], VOTES_PER_CLAIM),
                label=f"v{s[1]}:{s[0]['claim'][:40]}",
                phase="Verify",
            ))

    rt.log(f"{len(verify_fns)} verifier agent {'paralel' if len(verify_fns) > 1 else 'sıralı'} çalışıyor "
           f"(max {MAX_WORKERS} eşzamanlı)...")
    verdicts = rt.run_parallel(verify_fns, max_workers=min(MAX_WORKERS, len(verify_fns)))

    # Sonuçları claim bazında grupla
    voted = []
    for i, claim in enumerate(ranked_claims):
        claim_verdicts = verdicts[i * VOTES_PER_CLAIM:(i + 1) * VOTES_PER_CLAIM]
        valid = [v for v in claim_verdicts if v is not None]
        refuted_count = sum(1 for v in valid if v.get("refuted", False))
        errored = VOTES_PER_CLAIM - len(valid)
        survives = len(valid) >= REFUTATIONS_REQUIRED and refuted_count < REFUTATIONS_REQUIRED
        is_refuted = refuted_count >= REFUTATIONS_REQUIRED

        mark = "✓" if survives else ("✗" if is_refuted else "?")
        rt.log(f"  {mark} \"{claim['claim'][:50]}…\": {len(valid)-refuted_count}-{refuted_count}{' ('+str(errored)+' errored)' if errored else ''}")

        voted.append({**claim, "verdicts": valid, "refutedVotes": refuted_count,
                       "erroredVotes": errored, "survives": survives, "isRefuted": is_refuted})

    confirmed = [c for c in voted if c.get("survives")]
    killed = [c for c in voted if c.get("isRefuted")]
    unverified = [c for c in voted if not c.get("survives") and not c.get("isRefuted")]

    rt.log(f"{len(confirmed)} confirmed, {len(killed)} refuted, {len(unverified)} unverified")

    # ─── Phase 5: Synthesize ───
    rt.phase("5/5", "Synthesize — rapor sentezleniyor")

    if not confirmed:
        return _no_confirmed_result(question, angles, fetched_sources,
                                     all_claims, voted, confirmed, killed, unverified, dupes)

    # Build evidence blocks for synthesis
    confirmed_block = "\n".join(
        f"### [{i}] {c['claim']}\n"
        f"Vote: {len(c['verdicts'])-c['refutedVotes']}-{c['refutedVotes']} · "
        f"Source: {c.get('sourceUrl', '')} ({c.get('sourceQuality', '')})\n"
        f"Quote: \"{c.get('quote', '')}\"\n"
        for i, c in enumerate(confirmed)
    )
    killed_block = "\n## Refuted claims\n" + "\n".join(
        f"- \"{c['claim']}\" ({c.get('sourceUrl', '')})" for c in killed
    ) if killed else ""
    unverified_block = "\n## Unverified claims\n" + "\n".join(
        f"- \"{c['claim']}\" ({c.get('sourceUrl', '')})" for c in unverified
    ) if unverified else ""

    report = rt.agent_call(
        "## Synthesis: research report\n\n"
        f"**Question:** {question}\n\n"
        f"{len(confirmed)} claims survived {VOTES_PER_CLAIM}-vote adversarial verification.\n\n"
        "## Confirmed claims\n" + confirmed_block + "\n" + killed_block + unverified_block + "\n\n"
        "## Instructions\n"
        "1. Merge semantic duplicates.\n"
        "2. Group into coherent findings.\n"
        "3. Assign confidence: high (multiple primary sources), medium, low.\n"
        "4. Write a 3-5 sentence executive summary.\n"
        "5. Note caveats and open questions.\n\n"
        "Valid JSON only.",
        label="synthesize",
        phase="Synthesize",
    )

    if not report:
        return _salvage_result(question, angles, fetched_sources, all_claims,
                                voted, confirmed, killed, unverified, dupes)

    return {
        "question": question,
        "runtime": rt.name,
        **report,
        "refuted": [{"claim": c["claim"], "vote": f"{len(c['verdicts'])-c['refutedVotes']}-{c['refutedVotes']}",
                      "source": c.get("sourceUrl", "")} for c in killed],
        "unverified": [{"claim": c["claim"], "erroredVotes": c["erroredVotes"],
                         "source": c.get("sourceUrl", "")} for c in unverified],
        "sources": [{"url": s["url"], "quality": s["sourceQuality"],
                      "angle": s.get("angle", ""), "claimCount": len(s.get("claims", []))}
                     for s in fetched_sources],
        "stats": {
            "runtime": rt.name,
            "angles": len(angles),
            "sourcesFetched": len(fetched_sources),
            "claimsExtracted": len(all_claims),
            "claimsVerified": len(voted),
            "confirmed": len(confirmed),
            "killed": len(killed),
            "unverified": len(unverified),
            "afterSynthesis": len(report.get("findings", [])),
            "urlDupes": len(dupes),
            "agentCalls": 1 + len(angles) + len(fetched_sources) + (len(ranked_claims) * VOTES_PER_CLAIM) + 1,
        },
    }


# ─── Helpers ───

def _norm_url(u: str) -> str:
    m = re.match(r'^[a-z][a-z0-9+.-]*://(?:[^/?#\\]*@)?(?:www\.)?([^/:?#@\\]+)(?::\d+)?([^?#]*)', str(u).lower())
    return (m.group(1) + m.group(2).rstrip("/")) if m else str(u).lower()


def _rel_rank(r: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(r, 99)


def _imp_rank(i: str) -> int:
    return {"central": 0, "supporting": 1, "tangential": 2}.get(i, 99)


def _qual_rank(q: str) -> int:
    return {"primary": 0, "secondary": 1, "blog": 2, "forum": 3, "unreliable": 4}.get(q, 99)


def _scope_prompt(question: str) -> str:
    return (
        f"Decompose this research question into {ANGLES} complementary search angles.\n\n"
        "## Question\n" + question + "\n\n"
        f"## Task\nGenerate {ANGLES} distinct web search queries. "
        "Pick angles that suit the question's domain. "
        "Make queries specific, avoid redundancy.\n\n"
        'Return JSON: {"question":"...","summary":"...","angles":[{"label":"...","query":"...","rationale":"..."}]}'
    )


def _search_prompt(angle: dict, question: str) -> str:
    return (
        f"## Web Searcher: {angle['label']}\n\n"
        f"Research question: \"{question}\"\n"
        f"Your angle: {angle['label']} — {angle.get('rationale', '')}\n"
        f"Query: {angle['query']}\n\n"
        "Return the top 4-6 most relevant results. "
        "Rank by relevance to the ORIGINAL question. Skip SEO spam.\n\n"
        'Return JSON: {"results":[{"url":"...","title":"...","snippet":"...","relevance":"high|medium|low"}]}'
    )


def _fetch_prompt(source: dict, question: str, angle_label: str) -> str:
    return (
        f"## Source Extractor\n\nResearch question: \"{question}\"\n\n"
        f"URL: {source['url']}\nTitle: {source.get('title', '')}\nFound via: {angle_label}\n\n"
        "Extract 2-5 FALSIFIABLE claims with direct quotes. "
        "Rate source quality: primary/secondary/blog/forum/unreliable.\n\n"
        'Return JSON: {"claims":[{"claim":"...","quote":"...","importance":"central|supporting|tangential"}],"sourceQuality":"...","publishDate":"..."}'
    )


def _verify_prompt(claim: dict, question: str, voter_num: int, total_votes: int) -> str:
    return (
        f"## Adversarial Verifier (voter {voter_num+1}/{total_votes})\n\n"
        f"Be SKEPTICAL. Try to REFUTE this claim.\n\n"
        f"Research question: {question}\n\n"
        f"Claim: \"{claim['claim']}\"\n"
        f"Source: {claim.get('sourceUrl', '')} ({claim.get('sourceQuality', '')})\n"
        f"Quote: \"{claim.get('quote', '')}\"\n\n"
        "Refute if: unsupported/contradicted/low-quality source/marketing/outdated.\n"
        "Default to refuted=true if uncertain.\n\n"
        'Return JSON: {"refuted":true/false,"evidence":"...","confidence":"high|medium|low"}'
    )


def _empty_result(question, angles, fetched_sources, all_claims, dupes):
    return {
        "question": question,
        "summary": "No claims extracted from any source.",
        "findings": [], "refuted": [], "unverified": [],
        "sources": [{"url": s["url"], "quality": s["sourceQuality"]} for s in fetched_sources],
        "stats": {"angles": len(angles), "sources": len(fetched_sources), "claims": 0, "dupes": len(dupes)},
    }


def _no_confirmed_result(question, angles, fetched_sources, all_claims, voted, confirmed, killed, unverified, dupes):
    return {
        "question": question,
        "summary": f"{len(killed)} refuted, {len(unverified)} unverified. No claims survived.",
        "findings": [],
        "refuted": [{"claim": c["claim"], "vote": f"{len(c['verdicts'])-c['refutedVotes']}-{c['refutedVotes']}", "source": c.get("sourceUrl", "")} for c in killed],
        "unverified": [{"claim": c["claim"], "erroredVotes": c["erroredVotes"], "source": c.get("sourceUrl", "")} for c in unverified],
        "sources": [{"url": s["url"], "quality": s["sourceQuality"], "claimCount": len(s.get("claims", []))} for s in fetched_sources],
        "stats": {"angles": len(angles), "sources": len(fetched_sources), "claims": len(all_claims),
                   "verified": len(voted), "confirmed": 0, "killed": len(killed), "unverified": len(unverified)},
    }


def _salvage_result(question, angles, fetched_sources, all_claims, voted, confirmed, killed, unverified, dupes):
    return {
        "question": question,
        "summary": f"Synthesis failed. {len(confirmed)} verified claims unmerged.",
        "findings": [],
        "confirmed": [{"claim": c["claim"], "source": c.get("sourceUrl", ""), "quote": c.get("quote", ""),
                        "vote": f"{len(c['verdicts'])-c['refutedVotes']}-{c['refutedVotes']}"} for c in confirmed],
        "refuted": [{"claim": c["claim"], "vote": f"{len(c['verdicts'])-c['refutedVotes']}-{c['refutedVotes']}", "source": c.get("sourceUrl", "")} for c in killed],
        "unverified": [{"claim": c["claim"], "erroredVotes": c["erroredVotes"], "source": c.get("sourceUrl", "")} for c in unverified],
        "sources": [{"url": s["url"], "quality": s["sourceQuality"], "angle": s.get("angle", ""), "claimCount": len(s.get("claims", []))} for s in fetched_sources],
        "stats": {"angles": len(angles), "sourcesFetched": len(fetched_sources), "claimsExtracted": len(all_claims),
                   "claimsVerified": len(voted), "confirmed": len(confirmed), "killed": len(killed),
                   "unverified": len(unverified), "afterSynthesis": 0, "urlDupes": len(dupes)},
    }
