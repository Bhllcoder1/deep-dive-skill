"""Validation and normalisation of every model/search/runtime response entering the pipeline."""

from typing import Any, Dict, List, Optional

from core.urlsafe import normalize_public_url

QUALITY = {"primary", "secondary", "blog", "forum", "unreliable"}
IMPORTANCE = {"central", "supporting", "tangential"}


def text(value: Any, limit: int = 1000) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def fetchable_url(value: Any) -> Optional[str]:
    return normalize_public_url(value)


def valid_angles(value: Any, max_angles: int) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    angles, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            continue
        label, query = text(item.get("label"), 160), text(item.get("query"), 500)
        key = " ".join(query.lower().split())
        if not label or not query or key in seen:
            continue
        seen.add(key)
        angles.append({"label": label, "query": query, "rationale": text(item.get("rationale"), 500)})
        if len(angles) == max_angles:
            break
    return angles


def valid_search_results(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    results = []
    for item in value:
        if not isinstance(item, dict):
            continue
        url = fetchable_url(item.get("url"))
        if not url:
            continue
        relevance = text(item.get("relevance"), 20).lower()
        results.append({
            "url": url,
            "title": text(item.get("title"), 500),
            "snippet": text(item.get("snippet"), 2000),
            "relevance": relevance if relevance in {"high", "medium", "low"} else "low",
        })
    return results


def valid_extraction(value: Optional[dict], source: Dict[str, str]):
    if not value:
        return "unreliable", "", []
    quality = text(value.get("sourceQuality"), 30).lower()
    quality = quality if quality in QUALITY else "unreliable"
    claims = []
    raw_claims = value.get("claims")
    if isinstance(raw_claims, list):
        for item in raw_claims[:5]:
            if not isinstance(item, dict):
                continue
            claim, quote = text(item.get("claim"), 2000), text(item.get("quote"), 5000)
            importance = text(item.get("importance"), 30).lower()
            if not claim or not quote or importance not in IMPORTANCE:
                continue
            claims.append({"claim": claim, "quote": quote, "importance": importance,
                           "sourceUrl": source["url"], "sourceQuality": quality,
                           "angle": source["angle"]})
    return quality, text(value.get("publishDate"), 100), claims


def valid_verdict(value: Any) -> Optional[dict]:
    if not isinstance(value, dict) or not isinstance(value.get("refuted"), bool):
        return None
    return {
        "refuted": value["refuted"],
        "evidence": text(value.get("evidence"), 3000),
        "confidence": text(value.get("confidence"), 20).lower() or "low",
        "counterSource": fetchable_url(value.get("counterSource")) or "",
    }


def valid_report(value: Optional[dict], allowed_sources: set) -> Optional[dict]:
    """Accept a synthesis only if at least one finding cites a confirmed source."""
    if not value:
        return None
    summary = text(value.get("summary"), 5000)
    if not summary:
        return None
    findings = []
    for item in value.get("findings", []) if isinstance(value.get("findings"), list) else []:
        if not isinstance(item, dict):
            continue
        sources: List[str] = []
        for source in item.get("sources", []) if isinstance(item.get("sources"), list) else []:
            normalized = fetchable_url(source)
            if normalized in allowed_sources and normalized not in sources:
                sources.append(normalized)
        claim = text(item.get("claim"), 2000)
        if not claim or not sources:
            continue
        confidence = text(item.get("confidence"), 20).lower()
        findings.append({"claim": claim, "confidence": confidence if confidence in {"high", "medium", "low"} else "low",
                         "sources": sources, "evidence": text(item.get("evidence"), 5000),
                         "vote": text(item.get("vote"), 100)})
    if not findings:
        # The summary would be unsupported; the caller salvages the verified claims instead.
        return None
    return {"summary": summary, "findings": findings,
            "caveats": text(value.get("caveats"), 5000),
            "openQuestions": [text(item, 500) for item in value.get("openQuestions", [])
                              if text(item, 500)] if isinstance(value.get("openQuestions"), list) else []}


def rel_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value, 99)


def imp_rank(value: str) -> int:
    return {"central": 0, "supporting": 1, "tangential": 2}.get(value, 99)


def qual_rank(value: str) -> int:
    return {"primary": 0, "secondary": 1, "blog": 2, "forum": 3, "unreliable": 4}.get(value, 99)


def _norm_text(value: str) -> str:
    return " ".join(value.casefold().replace("’", "'").replace("“", '"').replace("”", '"').split())


def quote_in_source(quote: str, content: str) -> bool:
    """Whether the model's 'exact quote' really occurs in the fetched page (whitespace/case-insensitive)."""
    needle = _norm_text(quote).strip(" \"'.…")
    return bool(needle) and needle in _norm_text(content)
