"""Shared web search: one backend chain used by every runtime.

Order: Brave Search API (only if BRAVE_API_KEY is set) → Bing HTML → Wikipedia
(→ DuckDuckGo HTML only when DR_SEARCH_DDG=1). A self-hosted SearXNG (SearXNG_URL) is
queried by the runtimes before this chain and is the most dependable option.

DuckDuckGo is off by default: its HTML endpoint answers bursts with an anti-bot challenge
(HTTP 202 "anomaly"), which in practice blocks it. When enabled, requests are spaced out and
a challenge disables it for a while (circuit breaker). Bing's HTML results page is scraped
without a key (redirect links are decoded); Wikipedia's official API is the last resort:
sparse, but real sources instead of model-invented URLs.
"""

import base64
import html
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
from typing import Any, Callable, List, Optional

from core.logs import get_logger
from core.safefetch import USER_AGENT, secret_header_file
from core.urlsafe import normalize_public_url

_LOG = get_logger("websearch")
ENV_FILE = "~/.hermes/.env"  # fallback source for search API keys
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"  # HTML engines reject bot UAs
DDG_MIN_INTERVAL_S = 1.5
DDG_BLOCK_SECONDS = 300
_ddg_lock = threading.Lock()
_ddg_last = 0.0
_ddg_blocked_until = 0.0

_ANCHOR = re.compile(
    r'<a[^>]+class=["\'][^"\']*\bresult__a\b[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL)
_SNIPPET = re.compile(r'class=["\'][^"\']*\bresult__snippet\b[^"\']*["\'][^>]*>(.*?)</(?:a|td|div)>',
                      re.IGNORECASE | re.DOTALL)


def unwrap_ddg_url(url: str) -> str:
    """DuckDuckGo wraps hits as //duckduckgo.com/l/?uddg=<real url>; return the real one."""
    url = html.unescape(url).strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlsplit(url)
    if (parsed.hostname or "").lower().endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        return urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
    return url


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_ddg_html(page: str, max_results: int) -> List[dict]:
    """Extract public, de-duplicated results (url/title/snippet/relevance) from a DDG HTML page."""
    results: List[dict] = []
    seen = set()
    snippets = [_clean(m.group(1)) for m in _SNIPPET.finditer(page or "")]
    for index, match in enumerate(_ANCHOR.finditer(page or "")):
        url = normalize_public_url(unwrap_ddg_url(match.group(1)))
        title = _clean(match.group(2))
        if not url or not title or url in seen:
            continue
        seen.add(url)
        results.append({"url": url, "title": title,
                        "snippet": snippets[index] if index < len(snippets) else "",
                        "relevance": "medium"})
        if len(results) >= max_results:
            break
    return results


def ddg_blocked() -> bool:
    return time.monotonic() < _ddg_blocked_until


def reset_ddg_state() -> None:
    """Forget the throttle/breaker state (tests)."""
    global _ddg_last, _ddg_blocked_until
    _ddg_last = _ddg_blocked_until = 0.0


def ddg_html_search_with_curl(query: str, max_results: int, curl_path: str = "curl", *,
                              user_agent: str = BROWSER_UA, runner: Callable[..., Any] = subprocess.run,
                              sleep: Callable[[float], None] = time.sleep) -> List[dict]:
    global _ddg_last, _ddg_blocked_until
    if ddg_blocked():
        return []
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    with _ddg_lock:  # space requests out: bursts trigger the bot challenge
        wait = _ddg_last + DDG_MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            sleep(wait)
        _ddg_last = time.monotonic()
        try:
            proc = runner(
                [curl_path, "--silent", "--show-error", "--location", "--max-redirs", "3",
                 "--proto", "=http,https", "--connect-timeout", "5", "--max-time", "15",
                 *_proxy_args(), "-A", user_agent, "-w", "\n%{http_code}", "--", url],
                capture_output=True, text=True, errors="replace", timeout=20)
        except (OSError, subprocess.SubprocessError):
            return []
    if proc.returncode != 0:
        return []
    body, _, code = (proc.stdout or "").rpartition("\n")
    if code.strip() == "202" or "anomaly-modal" in body or "anomaly.js" in body:
        _ddg_blocked_until = time.monotonic() + DDG_BLOCK_SECONDS
        _LOG.warning(f"DuckDuckGo returned a bot challenge; skipping it for {DDG_BLOCK_SECONDS}s "
                     "(set SearXNG_URL or BRAVE_API_KEY for a dependable backend)")
        return []
    return parse_ddg_html(body, max_results)


def _search_key(name: str) -> str:
    """Search API key from the environment, else from ~/.hermes/.env (only these key names are read)."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        with open(os.path.expanduser(ENV_FILE), encoding="utf-8", errors="replace") as handle:
            for line in handle:
                key, _, val = line.strip().partition("=")
                if key == name and val.strip():
                    return val.strip().strip("\"'")
    except OSError:
        pass
    return ""


def _proxy_args() -> List[str]:
    """curl --proxy args from DR_SEARCH_PROXY (e.g. socks5h://127.0.0.1:9050 for Tor); [] when unset/invalid."""
    proxy = os.environ.get("DR_SEARCH_PROXY", "").strip()
    return ["--proxy", proxy] if re.match(r"^(socks5h?|socks4a?|https?)://[\w.\-]+(:\d+)?/?$", proxy) else []


def _curl_json(url: str, curl_path: str, headers: Optional[dict] = None,
               runner: Callable[..., Any] = subprocess.run) -> Optional[Any]:
    try:
        with secret_header_file(headers or {"Accept": "application/json"}) as header_path:
            proc = runner([curl_path, "--silent", "--fail", "--connect-timeout", "5", "--max-time", "15",
                           "-A", USER_AGENT, "-H", f"@{header_path}", "--", url],
                          capture_output=True, text=True, errors="replace", timeout=20)
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _curl_post_json(url: str, body: dict, headers: dict, curl_path: str = "curl",
                    runner: Callable[..., Any] = subprocess.run) -> Optional[Any]:
    """POST a JSON body (via stdin, never argv); credentials go in a 0600 header file."""
    try:
        with secret_header_file({"Content-Type": "application/json", **headers}) as header_path:
            proc = runner([curl_path, "--silent", "--fail", "--connect-timeout", "5", "--max-time", "20",
                           "--request", "POST", "-H", f"@{header_path}", "--data-binary", "@-", "--", url],
                          input=json.dumps(body), capture_output=True, text=True, errors="replace", timeout=25)
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def tavily_search(query: str, max_results: int, curl_path: str = "curl",
                  runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Tavily (free tier ~1000/month); needs TAVILY_API_KEY."""
    key = _search_key("TAVILY_API_KEY")
    if not key:
        return []
    data = _curl_post_json("https://api.tavily.com/search", {"query": query, "max_results": min(max_results, 20)},
                           {"Authorization": f"Bearer {key}"}, curl_path, runner)
    items = data.get("results") if isinstance(data, dict) else None
    out = (_result(i.get("url"), i.get("title"), i.get("content")) for i in items or [] if isinstance(i, dict))
    return [r for r in out if r][:max_results]


def serper_search(query: str, max_results: int, curl_path: str = "curl",
                  runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Serper.dev Google results (free signup credits); needs SERPER_API_KEY."""
    key = _search_key("SERPER_API_KEY")
    if not key:
        return []
    data = _curl_post_json("https://google.serper.dev/search", {"q": query, "num": min(max_results, 20)},
                           {"X-API-KEY": key}, curl_path, runner)
    items = data.get("organic") if isinstance(data, dict) else None
    out = (_result(i.get("link"), i.get("title"), i.get("snippet")) for i in items or [] if isinstance(i, dict))
    return [r for r in out if r][:max_results]


def _result(url: Any, title: Any, snippet: Any, relevance: str = "medium") -> Optional[dict]:
    safe = normalize_public_url(url)
    title = _clean(str(title or ""))
    return {"url": safe, "title": title, "snippet": _clean(str(snippet or "")), "relevance": relevance} \
        if safe and title else None


def brave_search(query: str, max_results: int, curl_path: str = "curl",
                 runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Brave Search API (https://api.search.brave.com); needs BRAVE_API_KEY."""
    key = _search_key("BRAVE_API_KEY")
    if not key:
        return []
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": query, "count": min(max_results, 20)})
    data = _curl_json(url, curl_path, {"Accept": "application/json", "X-Subscription-Token": key}, runner)
    items = ((data or {}).get("web") or {}).get("results") if isinstance(data, dict) else None
    results = [r for r in (_result(i.get("url"), i.get("title"), i.get("description"))
                           for i in (items or []) if isinstance(i, dict)) if r]
    return results[:max_results]


def wikipedia_search(query: str, max_results: int, curl_path: str = "curl",
                     runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Wikipedia's official search API (no key). Language: DR_WIKI_LANG (default en)."""
    lang = re.sub(r"[^a-z-]", "", os.environ.get("DR_WIKI_LANG", "en").lower()) or "en"
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": max_results})
    data = _curl_json(url, curl_path, None, runner)
    items = ((data or {}).get("query") or {}).get("search") if isinstance(data, dict) else None
    results = []
    for item in items or []:
        if isinstance(item, dict) and item.get("title"):
            title = str(item["title"])
            page = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
            found = _result(page, title, item.get("snippet"), "low")
            if found:
                results.append(found)
    return results[:max_results]


_BING_BLOCK = re.compile(r'<li class="b_algo"[^>]*>(.*?)</li>', re.IGNORECASE | re.DOTALL)
_BING_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_BING_SNIPPET = re.compile(r'<p[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)


def unwrap_bing_url(url: str) -> str:
    """Bing wraps hits as bing.com/ck/a?...&u=a1<base64url of the real URL>."""
    url = html.unescape(url).strip()
    parsed = urllib.parse.urlsplit(url)
    if (parsed.hostname or "").endswith("bing.com") and parsed.path.startswith("/ck/"):
        token = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
        if token.startswith("a1"):
            raw = token[2:]
            try:
                return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
            except ValueError:
                return ""
        return ""
    return url


def parse_bing_html(page: str, max_results: int) -> List[dict]:
    results: List[dict] = []
    seen = set()
    for block in _BING_BLOCK.finditer(page or ""):
        link = _BING_LINK.search(block.group(1))
        if not link:
            continue
        found = _result(unwrap_bing_url(link.group(1)), _clean(link.group(2)),
                        (_BING_SNIPPET.search(block.group(1)) or [None, ""])[1])
        if found and found["url"] not in seen:
            seen.add(found["url"])
            results.append(found)
            if len(results) >= max_results:
                break
    return results


def bing_search(query: str, max_results: int, curl_path: str = "curl", *,
                runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "en"})
    try:
        proc = runner([curl_path, "--silent", "--location", "--max-redirs", "3", "--proto", "=http,https",
                       "--connect-timeout", "5", "--max-time", "15", *_proxy_args(), "-A",
                       BROWSER_UA,
                       "-H", "Accept-Language: en", "--", url],
                      capture_output=True, text=True, errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_bing_html(proc.stdout, max_results) if proc.returncode == 0 else []


def web_search_chain(query: str, max_results: int, curl_path: str = "curl", *,
                     user_agent: str = BROWSER_UA, runner: Callable[..., Any] = subprocess.run) -> List[dict]:
    """Tavily / Serper / Brave (whichever is keyed) → [DuckDuckGo if DR_SEARCH_PROXY] → Bing → Wikipedia (→ DDG if DR_SEARCH_DDG=1); first non-empty wins,
    then thin lists are topped up from the keyless vertical APIs (core.searchapis)."""
    ddg = lambda: ddg_html_search_with_curl(query, max_results, curl_path, user_agent=user_agent, runner=runner)
    backends = [lambda: tavily_search(query, max_results, curl_path, runner),
                lambda: serper_search(query, max_results, curl_path, runner),
                lambda: brave_search(query, max_results, curl_path, runner)]
    # DuckDuckGo bot-challenges a plain IP, but works through a proxy (e.g. Tor): then it goes first.
    via_proxy = bool(_proxy_args())
    if via_proxy:
        backends.append(ddg)
    backends += [lambda: bing_search(query, max_results, curl_path, runner=runner),
                 lambda: wikipedia_search(query, max_results, curl_path, runner)]
    if not via_proxy and os.environ.get("DR_SEARCH_DDG") == "1":
        backends.append(ddg)
    from core.searchapis import top_up  # late import: searchapis builds on this module's helpers
    results: List[dict] = []
    for backend in backends:
        results = backend()
        if results:
            break
    return top_up(results, query, max_results, curl_path, runner)
