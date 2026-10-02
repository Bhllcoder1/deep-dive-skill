"""Keyless vertical search APIs (Stack Exchange, Hacker News, OpenAlex, GitHub, arXiv).

They top up a thin general-web result list; they never replace it. Selected with
DR_SEARCH_VERTICALS (comma list, default "stackexchange,hn,openalex"; empty disables)."""

import os
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Callable, List

from core.websearch import _curl_json, _result

DEFAULT_VERTICALS = "stackexchange,hn,openalex"


def _list(data: Any, key: str) -> list:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, list) else []


def stackexchange_search(query, max_results, curl_path="curl", runner=subprocess.run) -> List[dict]:
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode(
        {"order": "desc", "sort": "relevance", "q": query, "site": "stackoverflow", "pagesize": max_results})
    data = _curl_json(url, curl_path, None, runner)
    items = _list(data, "items")
    out = (_result(i.get("link"), i.get("title"), "Stack Overflow, score %s" % i.get("score"), "low")
           for i in items if isinstance(i, dict))
    return [r for r in out if r][:max_results]


def hn_search(query, max_results, curl_path="curl", runner=subprocess.run) -> List[dict]:
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": query, "tags": "story", "hitsPerPage": max_results})
    data = _curl_json(url, curl_path, None, runner)
    hits = _list(data, "hits")
    out = (_result(h.get("url") or "https://news.ycombinator.com/item?id=%s" % h.get("objectID"),
                   h.get("title"), "Hacker News, %s points" % h.get("points"), "low")
           for h in hits if isinstance(h, dict))
    return [r for r in out if r][:max_results]


def _abstract(inverted: Any) -> str:
    if not isinstance(inverted, dict):
        return ""
    words = {pos: w for w, positions in inverted.items() for pos in positions}
    return " ".join(words[p] for p in sorted(words))[:300]


def openalex_search(query, max_results, curl_path="curl", runner=subprocess.run) -> List[dict]:
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "per-page": max_results, "select": "title,doi,primary_location,abstract_inverted_index"})
    data = _curl_json(url, curl_path, None, runner)
    works = _list(data, "results")
    out = []
    for w in works:
        if isinstance(w, dict):
            link = ((w.get("primary_location") or {}).get("landing_page_url")) or w.get("doi")
            out.append(_result(link, w.get("title"), _abstract(w.get("abstract_inverted_index")), "low"))
    return [r for r in out if r][:max_results]


def github_search(query, max_results, curl_path="curl", runner=subprocess.run) -> List[dict]:
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": query, "per_page": max_results})
    data = _curl_json(url, curl_path, {"Accept": "application/vnd.github+json"}, runner)
    items = _list(data, "items")
    out = (_result(i.get("html_url"), i.get("full_name"), i.get("description"), "low")
           for i in items if isinstance(i, dict))
    return [r for r in out if r][:max_results]


def parse_arxiv(xml_text: str, max_results: int) -> List[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    ns = "{http://www.w3.org/2005/Atom}"
    out = (_result((e.findtext(ns + "id") or "").replace("http://", "https://", 1),
                   re.sub(r"\s+", " ", e.findtext(ns + "title") or ""),
                   re.sub(r"\s+", " ", e.findtext(ns + "summary") or "")[:300], "low")
           for e in root.iter(ns + "entry"))
    return [r for r in out if r][:max_results]


def arxiv_search(query, max_results, curl_path="curl", runner=subprocess.run) -> List[dict]:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": "all:" + query, "max_results": max_results})
    try:
        proc = runner([curl_path, "--silent", "--fail", "--max-time", "15", "--", url],
                      capture_output=True, text=True, errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_arxiv(proc.stdout, max_results) if proc.returncode == 0 else []


VERTICALS = {"stackexchange": stackexchange_search, "hn": hn_search, "openalex": openalex_search,
             "github": github_search, "arxiv": arxiv_search}


def top_up(results: List[dict], query: str, max_results: int, curl_path: str = "curl",
           runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Append vertical hits (deduplicated) until max_results is reached."""
    names = [n.strip() for n in os.environ.get("DR_SEARCH_VERTICALS", DEFAULT_VERTICALS).split(",") if n.strip()]
    out = list(results)
    seen = {r["url"] for r in out}
    for name in names:
        if len(out) >= max_results:
            break
        search = VERTICALS.get(name)
        for r in (search(query, max_results - len(out), curl_path, runner) if search else []):
            if r["url"] not in seen and len(out) < max_results:
                seen.add(r["url"])
                out.append(r)
    return out
