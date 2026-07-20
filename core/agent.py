"""
agent() — Universal LLM call with structured output.

Mimics Claude Code's agent(prompt, {label, phase, schema}) API while keeping a
single dict-or-None boundary for every runtime.
"""

import json
import os
import re
import shlex
import sys
import tempfile
import time
from typing import Any, Optional


_REQUEST_TIMEOUT_SECONDS = 60
_REQUEST_ATTEMPTS = 2
_JSON_DECODER = json.JSONDecoder()


def _detect_runtime() -> str:
    """Detect which platform we're running on."""
    if os.environ.get("HERMES_AGENT"):
        return "hermes"
    if os.environ.get("CLAUDE_CODE"):
        return "claude_code"
    if os.environ.get("AIDER_CHAT_MODE") or os.environ.get("AIDER_VERSION"):
        return "aider"
    if os.environ.get("OPENCLAW_MODE"):
        return "openclaw"
    if os.environ.get("CODEX_CLI"):
        return "codex"
    if os.environ.get("CLINE_MCP"):
        return "cline"
    try:
        import requests  # noqa: F401
        return "generic"
    except ImportError:
        return "minimal"


def _extract_json(text: str) -> Optional[dict]:
    """Return the first complete JSON object in an LLM response."""
    if not isinstance(text, str) or not text.strip():
        return None

    def decode_object(candidate: str, *, require_complete: bool) -> Optional[dict]:
        try:
            value, end = _JSON_DECODER.raw_decode(candidate.lstrip())
        except json.JSONDecodeError:
            return None
        if require_complete and candidate.lstrip()[end:].strip():
            return None
        return value if isinstance(value, dict) else None

    text = text.strip()
    parsed = decode_object(text, require_complete=True)
    if parsed is not None:
        return parsed

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        parsed = decode_object(match.group(1), require_complete=True)
        if parsed is not None:
            return parsed

    # raw_decode understands strings and nesting, unlike a greedy {.*} regex.
    # Only consider the first JSON-looking object in loose text.  Advancing to
    # a nested brace after a failed outer object would turn a truncated response
    # into a superficially valid partial result.
    match = re.search(r"\{\s*(?:\"|\})", text)
    return decode_object(text[match.start():], require_complete=False) if match else None


def _validate_schema(data: Any, schema: Optional[dict]) -> bool:
    """Validate the JSON Schema subset used by the research pipeline."""
    if not isinstance(data, dict) or (schema is not None and not isinstance(schema, dict)):
        return False
    if not schema:
        return True

    def validate(value: Any, rule: dict) -> bool:
        if not isinstance(rule, dict):
            return False

        has_expected_type = "type" in rule
        expected_type = rule.get("type")
        type_checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "boolean": lambda item: isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if has_expected_type:
            expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
            if (not expected_types
                    or not all(isinstance(name, str) and name in type_checks for name in expected_types)):
                return False
            if not any(type_checks[name](value) for name in expected_types):
                return False

        if "enum" in rule:
            allowed = rule["enum"]
            if not isinstance(allowed, list) or value not in allowed:
                return False

        object_rule = "object" in expected_types if has_expected_type else False
        object_rule = object_rule or "required" in rule or "properties" in rule
        if object_rule:
            if not isinstance(value, dict) and not has_expected_type:
                return False
            if isinstance(value, dict):
                required = rule.get("required", [])
                properties = rule.get("properties", {})
                if (not isinstance(required, list) or not all(isinstance(field, str) for field in required)
                        or not isinstance(properties, dict)):
                    return False
                if any(field not in value or value[field] is None for field in required):
                    return False
                for field, field_rule in properties.items():
                    if field in value and not validate(value[field], field_rule):
                        return False

        array_rule = "array" in expected_types if has_expected_type else False
        if array_rule and isinstance(value, list):
            min_items = rule.get("minItems")
            max_items = rule.get("maxItems")
            if "minItems" in rule and (not isinstance(min_items, int) or isinstance(min_items, bool)
                                       or min_items < 0 or len(value) < min_items):
                return False
            if "maxItems" in rule and (not isinstance(max_items, int) or isinstance(max_items, bool)
                                       or max_items < 0 or len(value) > max_items):
                return False
            if "items" in rule and any(not validate(item, rule["items"]) for item in value):
                return False
        return True

    return validate(data, schema)


def _completion_result(data: Any, schema: Optional[dict]) -> Optional[dict]:
    """Extract and validate an OpenAI-compatible chat completion response."""
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return None
    parsed = _extract_json(message["content"])
    return parsed if parsed is not None and _validate_schema(parsed, schema) else None


def _hermes_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Agent call via Hermes terminal + curl to a DeepSeek-compatible API."""
    from hermes_tools import terminal

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        result = terminal("cat ~/.env 2>/dev/null | grep -i deepseek | head -1 | cut -d= -f2", timeout=5)
        api_key = result.get("output", "").strip() if isinstance(result, dict) else ""
    if not api_key:
        result = terminal(
            "cat ~/.hermes/config.yaml 2>/dev/null | grep -A1 'deepseek' | grep 'api_key' | head -1 | awk '{print $2}'",
            timeout=5,
        )
        api_key = result.get("output", "").strip() if isinstance(result, dict) else ""
    if not api_key:
        print("[agent] WARNING: No DEEPSEEK_API_KEY set", file=sys.stderr)
        return None

    payload = {
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "You are a precise research agent. Return valid JSON only, no markdown, no commentary."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    payload_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        command = (
            "curl --silent --show-error --fail --connect-timeout 10 "
            f"--max-time {_REQUEST_TIMEOUT_SECONDS} https://api.deepseek.com/chat/completions "
            f"-H {shlex.quote('Content-Type: application/json')} "
            f"-H {shlex.quote('Authorization: Bearer ' + api_key)} "
            f"-d {shlex.quote('@' + payload_path)}"
        )
        result = terminal(command, timeout=_REQUEST_TIMEOUT_SECONDS + 5)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[agent] Hermes request failed: {exc}", file=sys.stderr)
        return None
    finally:
        if payload_path:
            try:
                os.unlink(payload_path)
            except OSError:
                pass

    output = result.get("output", "") if isinstance(result, dict) else ""
    try:
        parsed = _completion_result(json.loads(output), schema)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    if parsed is None:
        print("[agent] Hermes returned an invalid, incomplete, or failed response", file=sys.stderr)
    return parsed


def _claude_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Emit the marker consumed by Claude Code's JavaScript wrapper."""
    print("__CLAUDE_AGENT__:" + json.dumps({
        "prompt": prompt,
        "schema": schema,
        "label": kwargs.get("label", ""),
        "phase": kwargs.get("phase", ""),
    }))
    return None


def _generic_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Agent call through the requests library and an OpenAI-compatible API."""
    try:
        import requests as req
    except ImportError:
        print("[agent] ERROR: requests is required for the generic runtime", file=sys.stderr)
        return None

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("[agent] WARNING: No DEEPSEEK_API_KEY set", file=sys.stderr)
        return None
    api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
    if not api_base:
        print("[agent] ERROR: LLM_API_BASE is empty", file=sys.stderr)
        return None

    payload = {
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "You are a precise research agent. Return valid JSON only, no markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(_REQUEST_ATTEMPTS):
        try:
            response = req.post(
                f"{api_base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=(10, _REQUEST_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
            parsed = _completion_result(response.json(), schema)
            if parsed is None:
                print("[agent] LLM returned an invalid, incomplete, or schema-invalid response", file=sys.stderr)
            return parsed
        except req.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            retryable = status_code in (408, 429) or (isinstance(status_code, int) and status_code >= 500)
            if not retryable or attempt + 1 == _REQUEST_ATTEMPTS:
                detail = f"HTTP {status_code}" if status_code else "HTTP request"
                print(f"[agent] {detail} failed: {exc}", file=sys.stderr)
                return None
            time.sleep(0.25 * (attempt + 1))
        except (req.ConnectionError, req.Timeout) as exc:
            if attempt + 1 == _REQUEST_ATTEMPTS:
                print(f"[agent] Request failed after {_REQUEST_ATTEMPTS} attempts: {exc}", file=sys.stderr)
                return None
            time.sleep(0.25 * (attempt + 1))
        except req.RequestException as exc:
            print(f"[agent] Request failed: {exc}", file=sys.stderr)
            return None
        except (TypeError, ValueError) as exc:
            print(f"[agent] Invalid API response: {exc}", file=sys.stderr)
            return None
    return None


def agent(prompt: str, *, label: str = "", phase: str = "", schema: Optional[dict] = None) -> Optional[dict]:
    """Run a structured LLM call and return a schema-valid dict, or ``None``."""
    if not isinstance(prompt, str) or not prompt.strip():
        print("[agent] ERROR: prompt must be a non-empty string", file=sys.stderr)
        return None
    if not isinstance(label, str) or not isinstance(phase, str):
        print("[agent] ERROR: label and phase must be strings", file=sys.stderr)
        return None
    if schema is not None and not isinstance(schema, dict):
        print("[agent] ERROR: schema must be a dict or None", file=sys.stderr)
        return None

    phase_str = f"[{phase}] " if phase else ""
    label_str = f"{label}: " if label else ""
    print(f"  {phase_str}{label_str}agent started...", file=sys.stderr)

    try:
        runtime = _detect_runtime()
        if runtime == "hermes":
            result = _hermes_agent(prompt, schema, label=label, phase=phase)
        elif runtime == "claude_code":
            result = _claude_agent(prompt, schema, label=label, phase=phase)
        else:
            result = _generic_agent(prompt, schema, label=label, phase=phase)
    except Exception as exc:
        print(f"[agent] {runtime if 'runtime' in locals() else 'runtime'} error: {exc}", file=sys.stderr)
        result = None

    if result is not None:
        print(f"  {phase_str}{label_str}agent completed", file=sys.stderr)
    else:
        print(f"  {phase_str}{label_str}agent returned no result", file=sys.stderr)
    return result


def log(message: str) -> None:
    """Print a log message. Platform-aware."""
    print(f"[deep-research] {message}", file=sys.stderr)
