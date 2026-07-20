"""Portable web search and fetch helpers used by the generic runtime."""

import html
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple


_USER_AGENT = "DeepDive/1.0 (+https://github.com/)"
_SEARCH_TIMEOUT = 15
_MAX_RESULTS = 50
_MAX_FETCH_TIMEOUT = 120
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_FETCH_CHARS = 15_000


def _requests_available() -> bool:
    try:
        import requests  # noqa: F401
    except ImportError:
        return False
    return True


def _detect_web_capability() -> str:
    """Detect the best available web access method."""
    if os.environ.get("HERMES_AGENT"):
        return "hermes"
    if os.environ.get("CLAUDE_CODE"):
        return "claude"
    if os.environ.get("SearXNG_URL"):
        return "searxng"
    return "requests" if _requests_available() else "curl"


def _log(message: str) -> None:
    print(f"  [web] {message}", file=sys.stderr)


def _valid_url(url: object) -> Optional[str]:
    """Return a safe HTTP(S) URL, or ``None`` for malformed input."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > 8_192 or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    return url


def _search_args(query: object, max_results: object) -> Optional[Tuple[str, int]]:
    if not isinstance(query, str):
        _log("search query must be a non-empty string")
        return None
    query = query.strip()
    if not query or len(query) > 2_048:
        _log("search query is empty or too long")
        return None
    if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 1:
        _log("max_results must be a positive integer")
        return None
    return query, min(max_results, _MAX_RESULTS)


def _fetch_timeout(timeout: object) -> Optional[float]:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        _log("fetch timeout must be a positive number")
        return None
    return min(float(timeout), _MAX_FETCH_TIMEOUT)


class _TextExtractor(HTMLParser):
    """Tolerant HTML-to-text parser that ignores non-visible page content."""

    _IGNORED_TAGS = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in self._IGNORED_TAGS:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


class _DDGResultsParser(HTMLParser):
    """Extract DuckDuckGo HTML results without assuming well-formed markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._link: Optional[str] = None
        self._title_parts: list[str] = []
        self._snippet_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag.lower() == "a" and "result__a" in classes:
            self._link = attributes.get("href")
            self._title_parts = []
        if "result__snippet" in classes:
            self._snippet_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._link is not None:
            self.results.append({"url": self._link, "title": " ".join(self._title_parts), "snippet": ""})
            self._link = None
            self._title_parts = []
        if self._snippet_depth and tag.lower() in {"a", "div", "span"}:
            self._snippet_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._link is not None:
            self._title_parts.append(data)
        elif self._snippet_depth and self.results:
            snippet = self.results[-1]["snippet"]
            self.results[-1]["snippet"] = f"{snippet} {data}".strip()


def _decode_bytes(data: bytes, content_type: str = "") -> str:
    """Decode network bytes with header/meta hints and safe fallbacks."""
    header_match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", content_type, re.I)
    meta_match = re.search(br"<meta[^>]+charset\s*=\s*[\"']?([^\s/>\"']+)", data[:8_192], re.I)
    encodings = [header_match.group(1) if header_match else None]
    if meta_match:
        encodings.append(meta_match.group(1).decode("ascii", "ignore"))
    encodings.extend(["utf-8", "windows-1252"])
    for encoding in dict.fromkeys(encoding for encoding in encodings if encoding):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("utf-8", errors="replace")


def _text_from_html(raw: str) -> Optional[str]:
    if "\x00" in raw:
        return None
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        # HTMLParser is tolerant, but keep a safe fallback for unusual malformed input.
        text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:_MAX_FETCH_CHARS] or None


def _content_is_textual(content_type: str) -> bool:
    if not content_type:
        return True  # Some otherwise valid sites omit this header.
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type.startswith("text/") or any(token in media_type for token in ("html", "json", "xml"))


def _http_error(source: str, status_code: int, headers: Any) -> None:
    retry_after = headers.get("Retry-After") if headers else None
    detail = f"HTTP {status_code}"
    if status_code == 429 and retry_after:
        detail += f" (rate limited; retry after {retry_after})"
    _log(f"{source}: {detail}")


def _normalize_result_url(url: object) -> Optional[str]:
    if not isinstance(url, str):
        return None
    url = html.unescape(url.strip())
    if url.startswith("//"):
        url = f"https:{url}"
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        redirect_url = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if redirect_url:
            url = urllib.parse.unquote(redirect_url)
    return _valid_url(url)


def _clean_results(results: List[Dict[str, object]], max_results: int) -> list:
    cleaned = []
    seen = set()
    for result in results:
        url = _normalize_result_url(result.get("url"))
        if not url or url in seen:
            continue
        title = re.sub(r"\s+", " ", html.unescape(str(result.get("title", "")))).strip()
        snippet = re.sub(r"\s+", " ", html.unescape(str(result.get("snippet", "")))).strip()
        cleaned.append({
            "url": url,
            "title": title[:500] or url,
            "snippet": snippet[:2_000],
            "relevance": result.get("relevance") if result.get("relevance") in {"high", "medium", "low"} else "medium",
        })
        seen.add(url)
        if len(cleaned) >= max_results:
            break
    return cleaned


def _parse_ddg_html(page: str, max_results: int) -> list:
    parser = _DDGResultsParser()
    try:
        parser.feed(page)
        parser.close()
    except Exception:
        _log("DuckDuckGo returned malformed HTML")
    return _clean_results(parser.results, max_results)


def _search_headers() -> dict[str, str]:
    return {"User-Agent": _USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}


def search(query: str, max_results: int = 6) -> list:
    """Search the web and return ``url``, ``title``, ``snippet``, and relevance."""
    args = _search_args(query, max_results)
    if args is None:
        return []
    query, max_results = args
    capability = _detect_web_capability()

    if capability == "hermes":
        return _hermes_search(query, max_results)
    if capability == "claude":
        return _claude_search(query, max_results)
    if capability == "searxng":
        results = _searxng_search(query, max_results)
        if results:
            return results
        # A down SearXNG instance should not make the generic runtime unusable.
    if _requests_available():
        return _requests_search(query, max_results)
    return _curl_search(query, max_results)


def fetch(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a public HTTP(S) URL as bounded, visible plain text, or ``None``."""
    url = _valid_url(url)
    timeout = _fetch_timeout(timeout)
    if url is None:
        _log("refusing malformed or unsupported fetch URL")
        return None
    if timeout is None:
        return None

    capability = _detect_web_capability()
    if capability == "hermes":
        return _hermes_fetch(url, timeout)
    if capability == "claude":
        return _claude_fetch(url, timeout)
    if _requests_available():
        return _requests_fetch(url, timeout)
    return _curl_fetch(url, timeout)


# ─── Hermes implementations ───

def _hermes_search(query: str, max_results: int = 6) -> list:
    """Use Hermes' web_search tool via delegate_task subagent."""
    from hermes_tools import delegate_task

    delegate_task(
        goal=f"Search the web for: {query}",
        context=("Return a JSON array of up to " f"{max_results} results with url, title, snippet, and relevance (high/medium/low)."),
    )
    _log(f"Hermes search dispatched for: {query}")
    return []


def _hermes_fetch(url: str, timeout: float = 30) -> Optional[str]:
    """Fetch URL content using Hermes' terminal tool."""
    from hermes_tools import terminal

    # terminal() accepts a shell command; quote the validated URL for that shell.
    command = f"curl --fail --location --max-redirs 5 --max-time {timeout:g} --silent --show-error {shlex.quote(url)}"
    try:
        result = terminal(command, timeout=int(timeout) + 5)
    except Exception as exc:
        _log(f"Hermes fetch error: {exc}")
        return None
    if result.get("exit_code") == 0:
        return _text_from_html(result.get("output", ""))
    return None


# ─── Claude Code implementations ───

def _claude_search(query: str, max_results: int = 6) -> list:
    """Emit the marker consumed by Claude Code's runtime wrapper."""
    print(f"__CLAUDE_WebSearch__:{json.dumps({'query': query, 'max_results': max_results})}", file=sys.stderr)
    return []


def _claude_fetch(url: str, timeout: float = 30) -> Optional[str]:
    """Emit the marker consumed by Claude Code's runtime wrapper."""
    print(f"__CLAUDE_WebFetch__:{json.dumps({'url': url, 'timeout': timeout})}", file=sys.stderr)
    return None


# ─── Requests-based implementations ───

def _requests_search(query: str, max_results: int = 6) -> list:
    """Search DuckDuckGo HTML, then Google Custom Search when configured."""
    try:
        import requests

        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_search_headers(),
            timeout=(_SEARCH_TIMEOUT // 3, _SEARCH_TIMEOUT),
        )
        if response.status_code == 200:
            results = _parse_ddg_html(_decode_bytes(response.content, response.headers.get("Content-Type", "")), max_results)
            if results:
                return results
        else:
            _http_error("DuckDuckGo search", response.status_code, response.headers)
    except Exception as exc:
        _log(f"DuckDuckGo search error: {exc}")

    google_key = os.environ.get("GOOGLE_API_KEY")
    google_cx = os.environ.get("GOOGLE_CX")
    if not (google_key and google_cx):
        return []
    try:
        import requests

        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": google_key, "cx": google_cx, "q": query, "num": min(max_results, 10)},
            headers=_search_headers(),
            timeout=(_SEARCH_TIMEOUT // 3, _SEARCH_TIMEOUT),
        )
        if response.status_code != 200:
            _http_error("Google search", response.status_code, response.headers)
            return []
        data = response.json()
        if not isinstance(data, dict):
            _log("Google search returned an unexpected JSON payload")
            return []
        return _clean_results([
            {"url": item.get("link"), "title": item.get("title"), "snippet": item.get("snippet")}
            for item in data.get("items", [])
            if isinstance(item, dict)
        ], max_results)
    except Exception as exc:
        _log(f"Google search error: {exc}")
        return []


def _requests_fetch(url: str, timeout: float = 30) -> Optional[str]:
    """Fetch a bounded textual response with redirects and status checks."""
    try:
        import requests

        response = requests.get(
            url,
            headers=_search_headers(),
            timeout=(min(10, timeout), timeout),
            allow_redirects=True,
            stream=True,
        )
        try:
            if not 200 <= response.status_code < 300:
                _http_error(f"fetch {url}", response.status_code, response.headers)
                return None
            content_type = response.headers.get("Content-Type", "")
            if not _content_is_textual(content_type):
                _log(f"fetch {url}: unsupported content type {content_type!r}")
                return None
            chunks = []
            remaining = _MAX_RESPONSE_BYTES
            truncated = False
            for chunk in response.iter_content(chunk_size=16_384):
                if not chunk:
                    continue
                if len(chunk) > remaining:
                    chunks.append(chunk[:remaining])
                    truncated = True
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
                if not remaining:
                    truncated = True
                    break
            if truncated:
                _log(f"fetch {url}: response truncated at {_MAX_RESPONSE_BYTES} bytes")
            return _text_from_html(_decode_bytes(b"".join(chunks), content_type))
        finally:
            response.close()
    except Exception as exc:
        _log(f"fetch error for {url}: {exc}")
        return None


# ─── SearXNG implementation ───

def _searxng_search(query: str, max_results: int = 6) -> list:
    """Search a configured self-hosted SearXNG instance."""
    base_url = _valid_url(os.environ.get("SearXNG_URL", ""))
    if base_url is None:
        _log("SearXNG_URL is not a valid HTTP(S) URL")
        return []
    try:
        import requests

        response = requests.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json", "categories": "general"},
            headers=_search_headers(),
            timeout=(_SEARCH_TIMEOUT // 3, _SEARCH_TIMEOUT),
        )
        if response.status_code != 200:
            _http_error("SearXNG search", response.status_code, response.headers)
            return []
        data = response.json()
        if not isinstance(data, dict):
            _log("SearXNG returned an unexpected JSON payload")
            return []
        return _clean_results([
            {"url": item.get("url"), "title": item.get("title"), "snippet": item.get("content")}
            for item in data.get("results", [])
            if isinstance(item, dict)
        ], max_results)
    except Exception as exc:
        _log(f"SearXNG search error: {exc}")
        return []


# ─── Curl-based fallback ───

def _curl_search(query: str, max_results: int = 6) -> list:
    """Search DuckDuckGo HTML when the requests dependency is unavailable."""
    url = f"https://html.duckduckgo.com/html/?{urllib.parse.urlencode({'q': query})}"
    command = [
        "curl", "--fail", "--location", "--max-redirs", "5", "--connect-timeout", "5",
        "--max-time", str(_SEARCH_TIMEOUT), "--max-filesize", str(_MAX_RESPONSE_BYTES),
        "--silent", "--show-error", "--compressed", "-H", f"User-Agent: {_USER_AGENT}", url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=_SEARCH_TIMEOUT + 5)
        if result.returncode != 0:
            _log(f"curl search failed (exit {result.returncode}): {result.stderr.decode('utf-8', 'replace').strip()}")
            return []
        return _parse_ddg_html(_decode_bytes(result.stdout), max_results)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log(f"curl search error: {exc}")
        return []


def _curl_fetch(url: str, timeout: float = 30) -> Optional[str]:
    """Fetch bounded text with curl without invoking a shell."""
    command = [
        "curl", "--fail", "--location", "--max-redirs", "5", "--connect-timeout", str(min(10, timeout)),
        "--max-time", str(timeout), "--max-filesize", str(_MAX_RESPONSE_BYTES), "--silent", "--show-error",
        "--compressed", "-H", f"User-Agent: {_USER_AGENT}", "-H", "Accept: text/html,text/plain,application/json;q=0.9,*/*;q=0.1", url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout + 5)
        if result.returncode != 0:
            _log(f"curl fetch failed for {url} (exit {result.returncode}): {result.stderr.decode('utf-8', 'replace').strip()}")
            return None
        return _text_from_html(_decode_bytes(result.stdout))
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log(f"curl fetch error for {url}: {exc}")
        return None
