"""Local-CLI runtimes: one base class, ten thin subclasses.

A CLI runtime sends each agent prompt to a locally installed CLI on stdin and parses
a JSON object from its output. If the CLI is missing, fails, or prints no JSON, the
call falls back to ``GenericRuntime`` (OpenAI-compatible API). Search and fetch always
use the generic helpers, so they work even without any LLM API key.

The ``<NAME>_CLI`` variable doubles as the auto-detection flag and as an optional
command override. The override is split with ``shlex`` and run WITHOUT a shell
(no pipes/redirects/expansion); a value that is not an executable (for example
``CODEX_CLI=1``) is ignored and the default binary is used.
"""

import os
import shlex
import shutil
import subprocess
from typing import List, Optional, Tuple

from core.jsonparse import extract_json_object
from core.logs import get_logger

from .generic import GenericRuntime


_LOG = get_logger("runtime.cli")

class CliRuntime(GenericRuntime):
    """Base class: subclasses only declare data."""

    runtime_name: str = ""
    display_name: str = ""
    env_var: str = ""
    # Candidate commands in priority order; each is an argv prefix, e.g. ("gh", "copilot").
    commands: Tuple[Tuple[str, ...], ...] = ()
    extra_paths: Tuple[str, ...] = ()
    cli_timeout: int = 60

    def __init__(self):
        super().__init__()
        self._override_ignored = ""
        self._cli_cmd: Optional[List[str]] = self._resolve_cli()

    @property
    def name(self) -> str:
        return self.runtime_name

    # ── resolution ──
    @staticmethod
    def _executable(token: str) -> Optional[str]:
        if os.sep in token:
            path = os.path.expanduser(token)
            return path if os.path.isfile(path) and os.access(path, os.X_OK) else None
        return shutil.which(token)

    def _resolve_cli(self) -> Optional[List[str]]:
        raw = os.environ.get(self.env_var, "").strip()
        if raw:
            try:
                tokens = shlex.split(raw)
            except ValueError:
                tokens = []
            resolved = self._executable(tokens[0]) if tokens else None
            if resolved:
                return [resolved, *tokens[1:]]
            self._override_ignored = raw
        for candidate in self.commands:
            found = shutil.which(candidate[0])
            if found:
                return [found, *candidate[1:]]
        for path in self.extra_paths:
            found = self._executable(path)
            if found:
                return [found]
        return None

    # ── BaseRuntime ──
    def setup(self) -> bool:
        tag = f"[{self.runtime_name}]"
        if self._override_ignored:
            _LOG.warning(f"{tag} ⚠ {self.env_var}={self._override_ignored!r} is not an executable; using default lookup")
        if self._cli_cmd:
            self._init_http_client()  # search/fetch need no LLM key
            self._load_api_config()   # optional: lets a failing CLI fall back to the API
            self._ready = True
            _LOG.info(f"{tag} ✅ {self.display_name} CLI detected: {' '.join(self._cli_cmd)}")
            return True
        _LOG.warning(f"{tag} ⚠ No {self.display_name} CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        if not self._ready and not self.setup():
            return None
        if self._cli_cmd:
            result = self._run_cli(prompt, schema)
            if result is not None:
                return result
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def _run_cli(self, prompt: str, schema: Optional[dict]) -> Optional[dict]:
        tag = f"[{self.runtime_name}]"
        try:
            proc = subprocess.run(self._cli_cmd, input=prompt, text=True, capture_output=True,
                                  timeout=self.cli_timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            _LOG.info(f"{tag} CLI invocation failed: {type(exc).__name__}; falling back to generic")
            return None
        if proc.returncode != 0:
            _LOG.info(f"{tag} CLI exited {proc.returncode}; falling back to generic")
            return None
        result = extract_json_object((proc.stdout or "").strip() or (proc.stderr or "").strip(), schema)
        if result is None:
            _LOG.info(f"{tag} CLI output contained no JSON; falling back to generic")
        return result


class CodexRuntime(CliRuntime):
    runtime_name, display_name, env_var = "codex", "Codex", "CODEX_CLI"
    commands = (("codex",),)


class CursorRuntime(CliRuntime):
    runtime_name, display_name, env_var = "cursor", "Cursor Agent", "CURSOR_CLI"
    commands = (("cursor-agent",),)


class GeminiRuntime(CliRuntime):
    runtime_name, display_name, env_var = "gemini", "Gemini", "GEMINI_CLI"
    commands = (("gemini",),)


class CopilotRuntime(CliRuntime):
    runtime_name, display_name, env_var = "copilot", "Copilot", "COPILOT_CLI"
    commands = (("copilot",), ("gh", "copilot"))


class AmazonQRuntime(CliRuntime):
    runtime_name, display_name, env_var = "amazon_q", "Amazon Q", "AMAZON_Q_CLI"
    commands = (("q",),)


class WindsurfRuntime(CliRuntime):
    runtime_name, display_name, env_var = "windsurf", "Windsurf", "WINDSURF_CLI"
    commands = (("windsurf",),)


class KimiRuntime(CliRuntime):
    runtime_name, display_name, env_var = "kimi", "Kimi", "KIMI_CLI"
    commands = (("kimi",),)
    extra_paths = ("~/.kimi-code/bin/kimi",)


class GLMRuntime(CliRuntime):
    runtime_name, display_name, env_var = "glm", "GLM", "GLM_CLI"
    commands = (("glm",), ("zai",))


class MiniMaxRuntime(CliRuntime):
    runtime_name, display_name, env_var = "minimax", "MiniMax", "MINIMAX_CLI"
    commands = (("minimax",),)


class AntigravityRuntime(CliRuntime):
    # Antigravity's native multi-agent mode (/agent, /agents) is interactive-TUI only and
    # not scriptable via stdin/stdout, so it is deliberately not used.
    runtime_name, display_name, env_var = "antigravity", "Antigravity", "ANTIGRAVITY_CLI"
    commands = (("antigravity",),)
