"""
WebSearch and WebFetch — Universal web tools.
Mimics Claude Code's built-in WebSearch and WebFetch tools.
Works on any platform by detecting available capabilities.

WebSearch(query) -> list of {url, title, snippet}
WebFetch(url) -> str (page content as text)
"""

import json
import os
import re
import sys
import urllib.parse
from typing import Optional


def _detect_web_capability() -> str:
    """Detect best web access method."""
    if os.environ.get("HERMES_AGENT"):
        return "hermes"  # Has built-in web_search tool
    if os.environ.get("CLAUDE_CODE"):
        return "claude"  # Has built-in WebSearch/WebFetch
    if os.environ.get("SearXNG_URL"):
        return "searxng"  # Self-hosted SearXNG instance
    try:
        import requests  # noqa: F401
        return "requests"  # Can use Google/Bing via requests
    except ImportError:
        return "curl"  # Bare minimum


def search(query: str, max_results: int = 6) -> list:
    """
    Search the web for a query.
    Returns list of {url, title, snippet, relevance}.
    """
    capability = _detect_web_capability()

    if capability == "hermes":
        return _hermes_search(query, max_results)
    elif capability == "claude":
        return _claude_search(query, max_results)
    elif capability == "searxng":
        return _searxng_search(query, max_results)
    elif capability == "requests":
        return _requests_search(query, max_results)
    else:
        return _curl_search(query, max_results)


def fetch(url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch the content of a URL as plain text.
    Returns None on failure.
    """
    capability = _detect_web_capability()

    if capability == "hermes":
        return _hermes_fetch(url, timeout)
    elif capability == "claude":
        return _claude_fetch(url, timeout)
    elif capability == "requests":
        return _requests_fetch(url, timeout)
    else:
        return _curl_fetch(url, timeout)


# ─── Hermes implementations ───

def _hermes_search(query: str, max_results: int = 6) -> list:
    """Use Hermes' web_search tool via delegate_task subagent."""
    from hermes_tools import delegate_task

    # We can't call web_search directly from Python, so use a subagent
    result = delegate_task(
        goal=f"Search the web for: {query}",
        context=f"Return a JSON array of up to {max_results} results with url, title, snippet, and relevance (high/medium/low).",
    )
    # Note: this is async — result comes later. For sync use, fall back.
    print(f"  [web] Hermes search dispatched for: {query}", file=sys.stderr)
    return []


def _hermes_fetch(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch URL content using curl (Hermes terminal)."""
    from hermes_tools import terminal
    result = terminal(f"curl -sL --max-time {timeout} '{url}' 2>/dev/null | python3 -c \"import sys; from html.parser import HTMLParser; import re; p=HTMLParser(); d=re.sub(r'<[^>]+>', ' ', sys.stdin.read()); print(' '.join(d.split())[:10000])\"", timeout=timeout + 5)
    if result["exit_code"] == 0 and result["output"].strip():
        return result["output"].strip()
    return None


# ─── Claude Code implementations ───

def _claude_search(query: str, max_results: int = 6) -> list:
    """Use Claude Code's built-in WebSearch."""
    print(f"__CLAUDE_WebSearch__:{json.dumps({'query': query, 'max_results': max_results})}", file=sys.stderr)
    return []


def _claude_fetch(url: str, timeout: int = 30) -> Optional[str]:
    """Use Claude Code's built-in WebFetch."""
    print(f"__CLAUDE_WebFetch__:{json.dumps({'url': url})}", file=sys.stderr)
    return None


# ─── Requests-based implementations ───

def _requests_search(query: str, max_results: int = 6) -> list:
    """Search via DuckDuckGo (no API key needed, but rate limited)."""
    try:
        import requests
        # DuckDuckGo Lite (no JS needed)
        params = {"q": query, "format": "json", "max": max_results}
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for r in data.get("Results", [])[:max_results]:
                results.append({
                    "url": r.get("FirstURL", ""),
                    "title": r.get("Text", "").split(" - ")[0] if " - " in r.get("Text", "") else r.get("Text", ""),
                    "snippet": r.get("Text", ""),
                    "relevance": "medium",
                })
            # Also check Abstract
            if data.get("Abstract"):
                results.insert(0, {
                    "url": data.get("AbstractURL", ""),
                    "title": data.get("Heading", query),
                    "snippet": data.get("Abstract", ""),
                    "relevance": "high",
                })
            return results[:max_results]
    except Exception as e:
        print(f"  [web] DuckDuckGo search error: {e}", file=sys.stderr)

    # Fallback: try Google Custom Search if API key set
    google_key = os.environ.get("GOOGLE_API_KEY")
    google_cx = os.environ.get("GOOGLE_CX")
    if google_key and google_cx:
        try:
            import requests
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": google_key, "cx": google_cx, "q": query, "num": min(max_results, 10)},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return [
                    {"url": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", ""), "relevance": "medium"}
                    for r in data.get("items", [])[:max_results]
                ]
        except Exception as e:
            print(f"  [web] Google search error: {e}", file=sys.stderr)

    return []


def _requests_fetch(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch URL content using requests + html2text."""
    try:
        import requests
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if resp.status_code == 200:
            text = resp.text
            # Simple HTML to text
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:15000]
    except Exception as e:
        print(f"  [web] Fetch error for {url}: {e}", file=sys.stderr)
    return None


# ─── SearXNG implementation ───

def _searxng_search(query: str, max_results: int = 6) -> list:
    """Search using a self-hosted SearXNG instance."""
    searxng_url = os.environ.get("SearXNG_URL", "http://localhost:8888")
    try:
        import requests
        resp = requests.get(
            f"{searxng_url}/search",
            params={"q": query, "format": "json", "categories": "general"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", ""), "relevance": "medium"}
                for r in data.get("results", [])[:max_results]
            ]
    except Exception as e:
        print(f"  [web] SearXNG search error: {e}", file=sys.stderr)
    return []


# ─── Curl-based fallback ───

def _curl_search(query: str, max_results: int = 6) -> list:
    """Minimal search via curl + DuckDuckGo HTML parsing."""
    import subprocess
    encoded = urllib.parse.quote(query)
    cmd = f'curl -sL "https://html.duckduckgo.com/html/?q={encoded}" -H "User-Agent: Mozilla/5.0" 2>/dev/null'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        html = result.stdout
        # Extract search result links
        results = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            url = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if url and title:
                results.append({"url": url, "title": title, "snippet": "", "relevance": "medium"})
                if len(results) >= max_results:
                    break
        return results
    except Exception as e:
        print(f"  [web] curl search error: {e}", file=sys.stderr)
    return []


def _curl_fetch(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch URL content using curl."""
    import subprocess
    cmd = f'curl -sL --max-time {timeout} "{url}" -H "User-Agent: Mozilla/5.0" 2>/dev/null'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:15000]
    except Exception as e:
        print(f"  [web] curl fetch error for {url}: {e}", file=sys.stderr)
    return None
