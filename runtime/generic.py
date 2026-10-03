"""Portable fallback runtime using requests when available and curl otherwise."""

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from typing import Any, Callable, List, Optional, Tuple

from core.jsonparse import extract_json_object
from core.logs import get_logger
from core.parallel import run_bounded
from core.safefetch import (USER_AGENT as _USER_AGENT, fetch_text_with_curl, html_to_text,
                           jina_reader_fetch, secret_header_file)
from core.urlsafe import is_public_http_url, is_safe_to_connect
from core.websearch import parse_bing_html, web_search_chain

from .base import BaseRuntime


_API_TIMEOUT = 60
_CONNECT_TIMEOUT = 10
_FETCH_TIMEOUT = 30
_MAX_FETCH_BYTES = 2_000_000
_MAX_PARALLEL_WORKERS = 20
_PARALLEL_TIMEOUT = 120
_API_RETRIES = 2                      # extra attempts for transient failures
_RETRY_BASE_S = 1.0
_RETRY_CAP_S = 8.0
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


_LOG = get_logger("runtime.generic")

def _is_loopback_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost")


class GenericRuntime(BaseRuntime):
    """Generic Python runtime with no required dependency beyond Python and curl."""

    @property
    def name(self) -> str:
        return "generic"

    def __init__(self):
        self._api_key = ""
        self._api_url = ""
        self._ready = False
        self._has_requests = False
        self._curl_path: Optional[str] = None

    def setup(self) -> bool:
        """Validate API configuration and select an available HTTP client."""
        self._ready = False
        self._load_api_config()
        if not self._api_key:
            _LOG.error("[generic] ❌ DEEPSEEK_API_KEY bulunamadı.")
            _LOG.info("  export DEEPSEEK_API_KEY='sk-...'")
            return False
        if not self._api_url:
            _LOG.error("[generic] ❌ LLM_API_BASE geçerli bir http(s) API adresi değil.")
            return False

        if not self._init_http_client():
            return False

        self._ready = True
        client = "requests" if self._has_requests else "curl"
        _LOG.info(f"[generic] ✅ Runtime hazır ({client})")
        return True

    def _load_api_config(self) -> None:
        """Read the LLM API key and endpoint (also used by CLI runtimes for their fallback)."""
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self._dotenv_api_key()
        self._api_url = self._api_endpoint()
        if self._api_url.startswith("http://") and not _is_loopback_url(self._api_url):
            _LOG.warning("  [generic] ⚠ LLM_API_BASE is plain http:// — the API key would be sent unencrypted")

    def _init_http_client(self) -> bool:
        """Detect requests/curl for search and fetch (independent of any LLM API key)."""
        try:
            import requests  # noqa: F401
            self._has_requests = True
        except ImportError:
            self._has_requests = False

        self._curl_path = shutil.which("curl")
        if not self._has_requests:
            if not self._curl_path:
                _LOG.error("[generic] ❌ Ne requests ne curl bulunamadı. requests yükleyin veya curl sağlayın.")
                return False
            try:
                probe = subprocess.run(
                    [self._curl_path, "--version"], capture_output=True, text=True, timeout=3
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                _LOG.error(f"[generic] ❌ curl çalıştırılamadı: {exc}")
                return False
            if probe.returncode != 0:
                _LOG.error("[generic] ❌ curl kullanılabilir değil.")
                return False
        return True

    @staticmethod
    def _dotenv_api_key() -> str:
        """Read only an exact DEEPSEEK_API_KEY assignment from ~/.env."""
        try:
            with open(os.path.expanduser("~/.env"), encoding="utf-8") as env_file:
                for line in env_file:
                    match = re.match(r"\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(.*?)\s*$", line)
                    if match:
                        return match.group(1).strip().strip("\"'")
        except (OSError, UnicodeError):
            pass
        return ""

    @staticmethod
    def _api_endpoint() -> str:
        base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
        parsed = urllib.parse.urlsplit(base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return ""
        suffix = "/chat/completions"
        return base if parsed.path.endswith(suffix) else base + suffix

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call an OpenAI-compatible completion endpoint and return a JSON object."""
        if not isinstance(prompt, str) or not prompt.strip():
            self.log("agent çağrısı boş veya geçersiz prompt ile atlandı")
            return None
        if schema is not None and not isinstance(schema, dict):
            self.log("agent çağrısı geçersiz schema ile atlandı")
            return None
        if not self._ready and not self.setup():
            return None
        if not self._api_key or not self._api_url:
            # e.g. a CLI runtime whose CLI failed and no API fallback is configured: fail fast, no retries.
            _LOG.warning("  [generic] LLM API yapılandırılmamış (DEEPSEEK_API_KEY / LLM_API_BASE); çağrı atlandı")
            return None

        start = time.monotonic()
        phase_s = f"[{phase}] " if phase else ""
        label_s = f"{label}: " if label else ""
        _LOG.info(f"  {phase_s}{label_s}agent")

        payload = {
            "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "You are a precise research agent. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        if schema is not None:
            # json_object is supported by more OpenAI-compatible APIs than json_schema.
            payload["response_format"] = {"type": "json_object"}

        result: Optional[dict] = None
        for attempt in range(_API_RETRIES + 1):
            result, retryable = self._post_once(payload, schema)
            if result is not None or not retryable or attempt == _API_RETRIES:
                break
            delay = self._backoff(attempt)
            _LOG.warning(f"  [generic] geçici hata; {delay:.1f}s sonra yeniden deneniyor ({attempt + 1}/{_API_RETRIES})")
            time.sleep(delay)

        elapsed = time.monotonic() - start
        status = f"✓ {elapsed:.1f}s" if result is not None else f"❌ failed ({elapsed:.1f}s)"
        _LOG.info(f"  {phase_s}{label_s}{status}")
        return result

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Exponential backoff with jitter: ~1s, ~2s, ... capped at _RETRY_CAP_S."""
        return min(_RETRY_CAP_S, _RETRY_BASE_S * (2 ** attempt)) * (0.5 + random.random() / 2)

    def _post_once(self, payload: dict, schema: Optional[dict]) -> Tuple[Optional[dict], bool]:
        """One API attempt -> (result, retryable). curl is used only when requests is unavailable."""
        if self._has_requests:
            return self._requests_call(payload, schema)
        if self._curl_path:
            return self._curl_call(payload, schema)
        return None, False

    def _requests_call(self, payload: dict, schema: Optional[dict]) -> Tuple[Optional[dict], bool]:
        """Make the API request through requests, handling malformed API replies."""
        try:
            import requests
            response = requests.post(
                self._api_url,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(_CONNECT_TIMEOUT, _API_TIMEOUT),
            )
        except requests.RequestException as exc:
            _LOG.error(f"  [generic] requests error: {type(exc).__name__}")
            return None, True  # timeouts / connection resets are transient
        except Exception as exc:
            _LOG.error(f"  [generic] requests başlatılamadı: {type(exc).__name__}")
            return None, False

        try:
            if not response.ok:
                _LOG.error(f"  [generic] API hata {response.status_code}: {response.text[:200]}")
                return None, response.status_code in _RETRYABLE_STATUS
            result = self._completion_json(response.json(), schema)
            return result, result is None  # unusable model output: one more sample may fix it
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            _LOG.warning(f"  [generic] geçersiz API yanıtı: {exc}")
            return None, True
        finally:
            response.close()

    def _curl_call(self, payload: dict, schema: Optional[dict]) -> Tuple[Optional[dict], bool]:
        """Make the API request through curl (no shell; credentials never appear in argv)."""
        if not self._curl_path:
            return None, False
        payload_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as handle:
                json.dump(payload, handle)
                payload_path = handle.name
            with secret_header_file({"Authorization": f"Bearer {self._api_key}",
                                     "Content-Type": "application/json"}) as header_path:
                result = subprocess.run(
                    [
                        self._curl_path, "--silent", "--show-error", "--request", "POST",
                        "--connect-timeout", str(_CONNECT_TIMEOUT), "--max-time", str(_API_TIMEOUT),
                        "-H", f"@{header_path}", "--data-binary", f"@{payload_path}",
                        "-w", "\n%{http_code}", "--", self._api_url,
                    ],
                    capture_output=True, text=True, errors="replace", timeout=_API_TIMEOUT + _CONNECT_TIMEOUT + 5,
                )
            if result.returncode != 0:
                _LOG.error(f"  [generic] curl API hata: {result.stderr.strip()[:200]}")
                return None, True
            body, _, code = result.stdout.rpartition("\n")
            status = int(code) if code.isdigit() else 0
            if not 200 <= status < 300:
                _LOG.error(f"  [generic] API hata {status}: {body[:200]}")
                return None, status in _RETRYABLE_STATUS
            try:
                parsed = self._completion_json(json.loads(body), schema)
                return parsed, parsed is None
            except (json.JSONDecodeError, TypeError, KeyError, IndexError, ValueError) as exc:
                _LOG.warning(f"  [generic] curl geçersiz API yanıtı: {exc}")
                return None, True
        except (OSError, subprocess.TimeoutExpired) as exc:
            _LOG.error(f"  [generic] curl error: {type(exc).__name__}")
            return None, isinstance(exc, subprocess.TimeoutExpired)
        finally:
            if payload_path:
                try:
                    os.unlink(payload_path)
                except FileNotFoundError:
                    pass

    def _completion_json(self, data: Any, schema: Optional[dict]) -> Optional[dict]:
        if not isinstance(data, dict):
            raise ValueError("response is not an object")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("response has no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("response has no message")
        return extract_json_object(message.get("content"), schema)

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """SearXNG (if configured) → Brave (if keyed) → Bing → Wikipedia → Google CSE (if configured). DuckDuckGo is opt-in."""
        if not isinstance(query, str) or not query.strip() or not isinstance(max_results, int) or isinstance(max_results, bool):
            return []
        max_results = min(max_results, 50)
        if max_results <= 0:
            return []
        query = query.strip()[:2000]

        results = self._searxng_results(query, max_results)
        if not results and self._curl_path:
            results = web_search_chain(query, max_results, self._curl_path)
        if not results and self._has_requests:
            results = self._bing_requests_results(query, max_results)  # no curl installed
        if not results:
            results = self._google_results(query, max_results)
        return results[:max_results]

    def _searxng_results(self, query: str, max_results: int) -> List[dict]:
        """Query the self-hosted SearXNG instance named by SearXNG_URL (if configured).

        The instance address is operator-configured, so it is not subject to the
        public-URL rule that applies to fetched pages; its *results* still are."""
        base = (os.environ.get("SearXNG_URL") or os.environ.get("SEARXNG_URL") or "").strip().rstrip("/")
        parsed = urllib.parse.urlsplit(base)
        if not base or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return []
        url = f"{base}/search?" + urllib.parse.urlencode({"q": query, "format": "json", "categories": "general"})
        data: Any = None
        try:
            if self._has_requests:
                import requests
                response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=(_CONNECT_TIMEOUT, 15))
                data = response.json() if response.ok else None
                response.close()
            elif self._curl_path:
                proc = subprocess.run(
                    [self._curl_path, "--silent", "--fail", "--connect-timeout", str(_CONNECT_TIMEOUT),
                     "--max-time", "15", "-A", _USER_AGENT, "--", url],
                    capture_output=True, text=True, errors="replace", timeout=20)
                data = json.loads(proc.stdout) if proc.returncode == 0 else None
        except Exception:
            return []
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            return []
        results: List[dict] = []
        for item in data["results"]:
            if isinstance(item, dict):
                self._append_search_result(results, item.get("url"), item.get("title"), item.get("content"), "medium")
        return results[:max_results]

    def _bing_requests_results(self, query: str, max_results: int) -> List[dict]:
        try:
            import requests
            response = requests.get("https://www.bing.com/search", params={"q": query, "setlang": "en"},
                                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
                                             "Accept-Language": "en"}, timeout=(_CONNECT_TIMEOUT, 15))
            page = response.text if response.ok else ""
            response.close()
        except requests.RequestException:
            return []
        return parse_bing_html(page, max_results)

    def _google_results(self, query: str, max_results: int) -> List[dict]:
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        cx = os.environ.get("GOOGLE_CX", "").strip()
        if not (self._has_requests and api_key and cx):
            return []
        try:
            import requests
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cx, "q": query, "num": min(max_results, 10)},
                headers={"User-Agent": _USER_AGENT}, timeout=(_CONNECT_TIMEOUT, 15),
            )
            if not response.ok:
                return []
            data = response.json()
        except (requests.RequestException, ValueError, TypeError):
            return []
        finally:
            if "response" in locals():
                response.close()
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return []
        results: List[dict] = []
        for item in data["items"]:
            if isinstance(item, dict):
                self._append_search_result(results, item.get("link"), item.get("title"), item.get("snippet"), "medium")
        return results[:max_results]

    def _append_search_result(self, results: List[dict], url: Any, title: Any, snippet: Any, relevance: str) -> None:
        if not is_public_http_url(url) or any(item["url"] == url for item in results):
            return
        results.append({
            "url": url,
            "title": str(title or "").strip(),
            "snippet": str(snippet or "").strip(),
            "relevance": relevance,
        })

    def web_fetch(self, url: str) -> Optional[str]:
        """Fetch a public HTTP(S) URL with bounded response size and timeouts."""
        if not is_safe_to_connect(url):
            self.log("geçersiz, yerel veya özel ağa çözümlenen URL fetch için reddedildi")
            return None
        if self._has_requests:
            fetched = self._requests_fetch(url)
            if fetched is not None:
                return fetched
        fetched = self._curl_fetch(url)
        if not fetched and self._curl_path and os.environ.get("DR_FETCH_JINA") == "1":
            self.log("doğrudan fetch boş döndü; r.jina.ai yedeği kullanılıyor")
            return jina_reader_fetch(url, self._curl_path)
        return fetched

    def _requests_fetch(self, url: str) -> Optional[str]:
        try:
            import requests
            current_url = url
            for _ in range(4):
                response = requests.get(
                    current_url, headers={"User-Agent": _USER_AGENT}, timeout=(_CONNECT_TIMEOUT, _FETCH_TIMEOUT),
                    stream=True, allow_redirects=False,
                )
                if response.is_redirect:
                    location = response.headers.get("Location")
                    response.close()
                    current_url = urllib.parse.urljoin(current_url, location or "")
                    if not is_safe_to_connect(current_url):
                        return None
                    continue
                try:
                    if not response.ok:
                        return None
                    content_type = response.headers.get("Content-Type", "").lower()
                    if content_type and not content_type.startswith(("text/", "application/json", "application/xml", "application/xhtml+xml")):
                        return None
                    length = response.headers.get("Content-Length")
                    if length and int(length) > _MAX_FETCH_BYTES:
                        return None
                    body = bytearray()
                    for chunk in response.iter_content(16_384):
                        body.extend(chunk)
                        if len(body) > _MAX_FETCH_BYTES:
                            return None
                    return html_to_text(bytes(body).decode(response.encoding or "utf-8", errors="replace"))
                finally:
                    response.close()
        except (requests.RequestException, OSError, ValueError, TypeError):
            return None
        return None

    def _curl_fetch(self, url: str) -> Optional[str]:
        if not self._curl_path:
            return None
        return fetch_text_with_curl(url, self._curl_path, max_time=_FETCH_TIMEOUT,
                                    connect_timeout=_CONNECT_TIMEOUT, max_bytes=_MAX_FETCH_BYTES)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        """Run work in bounded worker threads while retaining input order."""
        if not isinstance(fn_list, (list, tuple)):
            raise TypeError("fn_list must be a list or tuple of callables")
        if not isinstance(max_workers, int) or isinstance(max_workers, bool) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if not all(callable(fn) for fn in fn_list):
            raise TypeError("fn_list must contain only callables")
        return run_bounded(
            list(fn_list), min(max_workers, _MAX_PARALLEL_WORKERS), timeout=_PARALLEL_TIMEOUT,
            on_error=lambda index, exc: self.log(f"parallel görev {index} hata verdi: {type(exc).__name__}"),
            on_timeout=lambda count: self.log(f"{count} parallel görev {_PARALLEL_TIMEOUT}s zaman sınırını aştı"),
        )
