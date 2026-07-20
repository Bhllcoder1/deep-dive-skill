"""
agent() — Universal LLM call with structured output.
Mimics Claude Code's agent(prompt, {label, phase, schema}) API.
Works on any platform by detecting the available runtime.

Usage:
    result = agent(prompt, label="my-agent", schema=MY_SCHEMA)
    # Returns dict matching schema, or None on failure
"""

import json
import os
import re
import sys
from typing import Any, Callable, Optional


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
    # Generic fallback — try to import requests
    try:
        import requests  # noqa: F401
        return "generic"
    except ImportError:
        return "minimal"


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling code fences and loose text."""
    if not text:
        return None
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` fences
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_schema(data: dict, schema: dict) -> bool:
    """Simple schema validation (no jsonschema dependency needed)."""
    if not schema:
        return True
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            return False
        if data[field] is None:
            return False
    return True


def _hermes_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Agent call via Hermes terminal + curl to DeepSeek API."""
    from hermes_tools import terminal

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        # Try to find it
        r = terminal("cat ~/.env 2>/dev/null | grep -i deepseek | head -1 | cut -d= -f2", timeout=5)
        api_key = r["output"].strip()

    if not api_key:
        # Try our config
        r = terminal("cat ~/.hermes/config.yaml 2>/dev/null | grep -A1 'deepseek' | grep 'api_key' | head -1 | awk '{print $2}'", timeout=5)
        api_key = r["output"].strip()

    system_msg = "You are a precise research agent. Return valid JSON only, no markdown, no commentary."

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        payload_path = f.name

    cmd = f'curl -s https://api.deepseek.com/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer {api_key}" -d @{payload_path} 2>/dev/null'
    result = terminal(cmd, timeout=60)
    os.unlink(payload_path)

    try:
        data = json.loads(result["output"])
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if parsed and _validate_schema(parsed, schema or {}):
            return parsed
        return parsed
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _claude_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Agent call using Claude Code's built-in agent() function.
    This function is called FROM within Claude Code's JS runtime.
    Claude Code injects 'agent' into the global scope.
    """
    # When running inside Claude Code, 'agent' is a global function.
    # We can't call it from Python directly, so we return a special marker
    # that the JS wrapper will intercept.
    print("__CLAUDE_AGENT__:" + json.dumps({
        "prompt": prompt,
        "schema": schema,
        "label": kwargs.get("label", ""),
        "phase": kwargs.get("phase", ""),
    }))
    return None  # The JS wrapper reads stdout and replaces this


def _generic_agent(prompt: str, schema: Optional[dict] = None, **kwargs) -> Optional[dict]:
    """Agent call using plain requests library."""
    import requests as req

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1")

    if not api_key:
        print("[agent] WARNING: No DEEPSEEK_API_KEY set", file=sys.stderr)
        return None

    system_msg = "You are a precise research agent. Return valid JSON only, no markdown."

    payload = {
        "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = req.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if parsed and _validate_schema(parsed, schema or {}):
            return parsed
        return parsed
    except Exception as e:
        print(f"[agent] Error: {e}", file=sys.stderr)
        return None


def agent(prompt: str, *, label: str = "", phase: str = "", schema: Optional[dict] = None) -> Optional[dict]:
    """
    Universal agent() call — works on any platform.

    Args:
        prompt: The instruction prompt for the LLM
        label: Agent label (for logging/progress)
        phase: Phase name (for progress tracking)
        schema: Optional JSON schema for structured output validation

    Returns:
        Parsed dict matching schema, or None on failure
    """
    phase_str = f"[{phase}] " if phase else ""
    label_str = f"{label}: " if label else ""
    print(f"  {phase_str}{label_str}agent started...", file=sys.stderr)

    runtime = _detect_runtime()
    result = None

    if runtime == "hermes":
        result = _hermes_agent(prompt, schema, label=label, phase=phase)
    elif runtime == "claude_code":
        result = _claude_agent(prompt, schema, label=label, phase=phase)
    else:
        result = _generic_agent(prompt, schema, label=label, phase=phase)

    if result:
        print(f"  {phase_str}{label_str}agent completed", file=sys.stderr)
    else:
        print(f"  {phase_str}{label_str}agent returned no result", file=sys.stderr)

    return result


def log(message: str) -> None:
    """Print a log message. Platform-aware."""
    print(f"[deep-research] {message}", file=sys.stderr)
