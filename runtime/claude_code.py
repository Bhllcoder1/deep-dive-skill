"""Claude Code runtime adapter.

When running under the Claude Code wrapper, this adapter writes line-framed
``__CLAUDE_*__`` requests to stderr.  stderr is deliberate: stdout must stay
available for the harness's final JSON result.  The bundled wrapper currently
does not send tool results back, so the adapter retains the generic API
fallback when a native result is unavailable.
"""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Mapping, Optional
from urllib.parse import urlparse

from .base import BaseRuntime


_MARKER_TYPES = {"AGENT", "WebSearch", "WebFetch", "PARALLEL"}
_MAX_SEARCH_RESULTS = 20


class ClaudeCodeRuntime(BaseRuntime):
    """Runtime adapter for Claude Code, with a DeepSeek fallback."""

    @property
    def name(self) -> str:
        return "claude_code"

    def __init__(self):
        self._ready = False
        self._in_claude = os.environ.get("CLAUDE_CODE") == "1"
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    def setup(self) -> bool:
        """Check whether either the Claude bridge or fallback is available."""
        if self._in_claude:
            print("[claude_code] Claude Code runtime detected", file=sys.stderr)
            self._ready = True
            return True
        if self._api_key:
            print("[claude_code] Claude Code unavailable; using generic fallback", file=sys.stderr)
            self._ready = True
            return True
        print("[claude_code] Claude Code unavailable and no API key configured", file=sys.stderr)
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

    @staticmethod
    def _matches_schema(data: dict, schema: Optional[dict]) -> bool:
        """Validate the small schema subset the runtime promises to enforce."""
        if not isinstance(data, dict):
            return False
        if not schema:
            return True
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            return False
        return all(data.get(key) is not None for key in required)

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

        # The current bridge is request-only.  Do not pretend that a marker
        # produced a response; callers get a real fallback result or None.
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

        api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com").rstrip("/")
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
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
            result = self._extract_json(content, schema)
            if result is None:
                self.log("agent fallback returned malformed or schema-incomplete JSON")
            return result
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
            self.log(f"agent fallback error: {exc}")
            return None

    def _extract_json(self, text: str, schema: Optional[dict] = None) -> Optional[dict]:
        """Extract one complete JSON object, tolerating prose and code fences."""
        if not isinstance(text, str) or not text.strip():
            return None

        candidates = [text.strip()]
        candidates.extend(match.group(1).strip() for match in re.finditer(
            r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE
        ))
        decoder = json.JSONDecoder()
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if self._matches_schema(parsed, schema):
                    return parsed
            except json.JSONDecodeError:
                pass

            # raw_decode finds balanced objects and avoids the old greedy
            # ``{.*}`` regex, which swallowed multiple/partial JSON objects.
            start = 0
            while True:
                start = candidate.find("{", start)
                if start < 0:
                    break
                try:
                    parsed, _ = decoder.raw_decode(candidate[start:])
                except json.JSONDecodeError:
                    start += 1
                    continue
                if self._matches_schema(parsed, schema):
                    return parsed
                start += 1
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

        try:
            response = subprocess.run(
                ["curl", "-sL", "--max-time", "15", "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query),
                 "-H", "User-Agent: Mozilla/5.0"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if response.returncode != 0:
                self.log(f"web search fallback failed with exit code {response.returncode}")
                return []
            results = []
            for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.stdout, re.DOTALL):
                url = match.group(1).strip()
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if url and title:
                    results.append({"url": url, "title": title, "snippet": "", "relevance": "medium"})
                if len(results) >= max_results:
                    break
            return results
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"web search fallback error: {exc}")
            return []

    def web_fetch(self, url: str) -> Optional[str]:
        """Fetch an HTTP(S) URL through the bridge or curl fallback."""
        if not isinstance(url, str):
            self.log("web fetch rejected: URL must be a string")
            return None
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            self.log("web fetch rejected: URL must be absolute HTTP(S)")
            return None

        if self._in_claude:
            self._emit_marker("WebFetch", {"url": url})

        try:
            response = subprocess.run(
                ["curl", "-sL", "--max-time", "30", url, "-H", "User-Agent: Mozilla/5.0"],
                capture_output=True,
                text=True,
                timeout=35,
            )
            if response.returncode != 0 or not response.stdout.strip():
                return None
            text = re.sub(r"<script[^>]*>.*?</script>", "", response.stdout, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text).strip()[:15000] or None
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"web fetch fallback error: {exc}")
            return None

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

        results = [None] * len(fn_list)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fn): index for index, fn in enumerate(fn_list)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    self.log(f"parallel worker {index} error: {exc}")
        return results

    def phase(self, name: str, detail: str = "") -> None:
        """Report progress without corrupting JSON emitted on stdout."""
        if self._in_claude:
            print(f"  ◇ Phase {name}: {detail}" if detail else f"  ◇ Phase {name}", file=sys.stderr)
        else:
            line = "─" * 50
            print(f"\n{line}\n PHASE: {name}\n{line}", file=sys.stderr)

    def log(self, message: str) -> None:
        print(f"  • {message}", file=sys.stderr)
