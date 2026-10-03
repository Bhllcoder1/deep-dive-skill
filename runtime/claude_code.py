"""Claude Code runtime adapter.

When running under the Claude Code wrapper, this adapter writes line-framed
``__CLAUDE_*__`` requests to stderr.  stderr is deliberate: stdout must stay
available for the harness's final JSON result.  The bundled wrapper currently
does not send tool results back, so the adapter retains the generic API
fallback when a native result is unavailable.
"""

import json
import os
import shlex
import shutil
import sys
from typing import Any, Callable, List, Mapping, Optional

from core.jsonparse import extract_json_object
from core.logs import get_logger
from core.parallel import run_bounded
from core.safefetch import fetch_text_with_curl
from core.urlsafe import is_public_http_url
from core.websearch import web_search_chain

from .base import BaseRuntime
from .cli import run_cli_json
from .generic import GenericRuntime


_MARKER_TYPES = {"AGENT", "WebSearch", "WebFetch", "PARALLEL"}
_MAX_SEARCH_RESULTS = 20


_LOG = get_logger("runtime.claude_code")

_CLAUDE_HEADLESS = ("--tools", "", "--no-session-persistence", "--output-format", "text")
_MAX_CLI_FAILURES = 3


class ClaudeCodeRuntime(BaseRuntime):
    """Runtime adapter for Claude Code.

    Agent calls use the real response channel ``claude -p`` (headless print mode; verified
    against the installed CLI) with tools disabled, run in an empty temp directory. The
    stderr bridge markers are still emitted for the Node wrapper, but they are request-only,
    so the DeepSeek-compatible API is the fallback when ``claude`` is unavailable or fails.
    Opt out of the headless call with ``DR_CLAUDE_HEADLESS=0``; ``CLAUDE_CLI`` overrides the command."""

    @property
    def name(self) -> str:
        return "claude_code"

    def __init__(self):
        self._ready = False
        self._in_claude = (os.environ.get("CLAUDE_CODE") == "1" or os.environ.get("CLAUDECODE") == "1"
                           or bool(os.environ.get("CLAUDE_CODE_ENTRYPOINT")))
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self._claude_cmd = self._resolve_claude()
        self._failures = 0

    @staticmethod
    def _resolve_claude() -> Optional[list]:
        if os.environ.get("DR_CLAUDE_HEADLESS", "1") == "0":
            return None
        raw = os.environ.get("CLAUDE_CLI", "").strip()
        if raw:
            try:
                tokens = shlex.split(raw)
            except ValueError:
                tokens = []
            found = shutil.which(tokens[0]) if tokens else None
            return [found, *tokens[1:]] if found else None
        found = shutil.which("claude")
        return [found, "-p", *_CLAUDE_HEADLESS] if found else None

    def setup(self) -> bool:
        """Ready when the headless `claude` CLI or the API fallback is usable."""
        if self._claude_cmd:
            _LOG.info(f"[claude_code] headless agent: {' '.join(self._claude_cmd[:2])} …"
                      + (" (inside Claude Code)" if self._in_claude else ""))
            self._ready = True
            return True
        if self._api_key:
            _LOG.warning("[claude_code] `claude` CLI unavailable; using the generic API fallback")
            self._ready = True
            return True
        _LOG.error("[claude_code] neither the `claude` CLI nor DEEPSEEK_API_KEY is available")
        return False

    def _emit_marker(self, marker_type: str, data: Mapping[str, Any]) -> None:
        """Emit one valid, line-framed bridge request without corrupting stdout."""
        if marker_type not in _MARKER_TYPES:
            raise ValueError(f"unsupported Claude marker type: {marker_type!r}")
        if not isinstance(data, Mapping):
            raise TypeError("Claude marker payload must be a mapping")
        try:
            payload = json.dumps(dict(data), ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Claude marker payload is not JSON serializable: {exc}") from exc
        print(f"__CLAUDE_{marker_type}__:{payload}", file=sys.stderr, flush=True)

    @staticmethod
    def _valid_schema(schema: Optional[dict]) -> bool:
        return schema is None or isinstance(schema, Mapping)

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Claude's bridge when present, then use the configured fallback."""
        if not isinstance(prompt, str) or not prompt.strip():
            self.log("agent call rejected: prompt must be a non-empty string")
            return None
        if not self._valid_schema(schema):
            self.log("agent call rejected: schema must be an object")
            return None
        if not isinstance(label, str) or not isinstance(phase, str):
            self.log("agent call rejected: label and phase must be strings")
            return None

        if self._in_claude:
            self._emit_marker("AGENT", {
                "prompt": prompt,
                "schema": schema,
                "label": label,
                "phase": phase,
            })

        # The marker bridge is request-only, so it never produces a result by itself.
        if self._claude_cmd and self._failures < _MAX_CLI_FAILURES:
            result = run_cli_json(self._claude_cmd, prompt, schema, prompt_mode="stdin",
                                  timeout=120, tag="claude_code")
            self._failures = 0 if result is not None else self._failures + 1
            if result is not None:
                return result
        return self._generic_agent_call(prompt, schema, label, phase)

    def _generic_agent_call(self, prompt: str, schema: Optional[dict] = None,
                            label: str = "", phase: str = "") -> Optional[dict]:
        """Use the OpenAI-compatible fallback and reject malformed responses."""
        if not self._api_key:
            self.log("agent result unavailable: Claude bridge has no response channel and no API key is configured")
            return None
        try:
            import requests
        except ImportError:
            self.log("agent fallback unavailable: requests is not installed")
            return None

        payload = {
            "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "You are a precise research agent. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        endpoint = GenericRuntime._api_endpoint()  # validated http(s) URL, same default as every runtime
        if not endpoint:
            self.log("agent fallback unavailable: LLM_API_BASE is not a valid http(s) URL")
            return None
        try:
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if response.status_code != 200:
                self.log(f"agent fallback failed with HTTP {response.status_code}: {response.text[:200]}")
                return None
            data = response.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            if not isinstance(choices, list) or not choices:
                self.log("agent fallback returned no choices")
                return None
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            result = extract_json_object(content, schema)
            if result is None:
                self.log("agent fallback returned malformed or schema-incomplete JSON")
            return result
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
            self.log(f"agent fallback error: {exc}")
            return None

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """Search via Claude's bridge or DuckDuckGo's HTML fallback."""
        if not isinstance(query, str) or not query.strip():
            self.log("web search rejected: query must be a non-empty string")
            return []
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            self.log("web search rejected: max_results must be an integer")
            return []
        max_results = max(1, min(max_results, _MAX_SEARCH_RESULTS))

        if self._in_claude:
            self._emit_marker("WebSearch", {"query": query, "max_results": max_results})

        return web_search_chain(query, max_results, "curl", user_agent="Mozilla/5.0")

    def web_fetch(self, url: str) -> Optional[str]:
        """Fetch a public HTTP(S) URL through the bridge or the shared safe curl fetch."""
        if not isinstance(url, str):
            self.log("web fetch rejected: URL must be a string")
            return None
        if not is_public_http_url(url):
            self.log("web fetch rejected: URL must be a public absolute HTTP(S) URL")
            return None

        if self._in_claude:
            self._emit_marker("WebFetch", {"url": url})
        return fetch_text_with_curl(url, "curl", user_agent="Mozilla/5.0", max_time=30)

    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 5) -> List[Any]:
        """Run valid callables with an enforced worker limit and ordered output."""
        if not isinstance(fn_list, list) or not all(callable(fn) for fn in fn_list):
            self.log("parallel call rejected: fn_list must contain only callables")
            return []
        if not fn_list:
            return []
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            self.log("parallel call rejected: max_workers must be a positive integer")
            return [None] * len(fn_list)
        max_workers = min(max_workers, len(fn_list))

        if self._in_claude:
            self._emit_marker("PARALLEL", {"count": len(fn_list), "max_workers": max_workers})

        return run_bounded(
            fn_list, max_workers,
            on_error=lambda index, exc: self.log(f"parallel worker {index} error: {exc}"),
        )
