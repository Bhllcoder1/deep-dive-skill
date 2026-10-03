"""Token-saving text helpers: query-aware excerpts, quote context, near-duplicate claims."""

import re
from typing import Iterable, List, Set

_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
_STOP = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "how", "what", "why", "does",
         "ve", "bir", "bu", "için", "ile", "nasıl", "nedir", "mi", "mı"}


def words(text: str) -> Set[str]:
    return {w for w in (m.group(0).casefold() for m in _WORD.finditer(text or "")) if w not in _STOP}


def excerpt(content: str, query: str, limit: int) -> str:
    """Return at most ``limit`` chars of ``content``: the paragraphs that best match ``query``,
    kept in their original order. Short content is returned unchanged."""
    if len(content) <= limit:
        return content
    terms = words(query)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|(?<=[.!?])\s{2,}", content) if p.strip()]
    if len(paragraphs) < 3:
        return content[:limit]
    scored = sorted(range(len(paragraphs)),
                    key=lambda i: (-len(terms & words(paragraphs[i])) / (1 + len(paragraphs[i]) / 800), i))
    chosen, used = set(), 0
    for index in [0] + scored:  # always keep the lead paragraph (title/definition)
        size = len(paragraphs[index]) + 2
        if index in chosen or (used + size > limit and chosen):
            continue
        chosen.add(index)
        used += size
    return "\n\n".join(paragraphs[i][:limit] for i in sorted(chosen))[:limit]


def context_around(content: str, quote: str, radius: int = 350) -> str:
    """The text surrounding ``quote`` in ``content`` (case/whitespace-insensitive), or ''."""
    flat = " ".join(content.split())
    needle = " ".join(quote.split()).strip(" \"'.…")
    position = flat.casefold().find(needle.casefold()) if needle else -1
    if position < 0:
        return ""
    return flat[max(0, position - radius):position + len(needle) + radius]


def similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Jaccard overlap of content words; cheap near-duplicate test for claims."""
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= threshold


def dedupe_claims(claims: Iterable[dict], threshold: float = 0.75) -> List[dict]:
    """Drop later claims that restate an earlier one; the survivor lists the other sources in ``alsoIn``."""
    kept: List[dict] = []
    for claim in claims:
        twin = next((k for k in kept if similar(k["claim"], claim["claim"], threshold)), None)
        if twin is None:
            kept.append(claim)
        elif claim["sourceUrl"] != twin["sourceUrl"]:
            twin.setdefault("alsoIn", []).append(claim["sourceUrl"])
    return kept
