"""Shared DuckDuckGo HTML search: the one parser and the one curl search call."""

import html
import re
import subprocess
import urllib.parse
from typing import Any, Callable, List

from core.safefetch import USER_AGENT
from core.urlsafe import normalize_public_url

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


def ddg_html_search_with_curl(query: str, max_results: int, curl_path: str = "curl", *,
                              user_agent: str = USER_AGENT, runner: Callable[..., Any] = subprocess.run
                              ) -> List[dict]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        proc = runner(
            [curl_path, "--silent", "--show-error", "--fail", "--location", "--max-redirs", "3",
             "--proto", "=http,https", "--connect-timeout", "5", "--max-time", "15",
             "-A", user_agent, "--", url],
            capture_output=True, text=True, errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_ddg_html(proc.stdout, max_results) if proc.returncode == 0 else []
