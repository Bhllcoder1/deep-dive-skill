"""Local-CLI runtimes: one base class, ten thin subclasses.

A CLI runtime sends each agent prompt to a locally installed agent CLI in its
non-interactive ("headless") mode and parses a JSON object from its output. If the CLI
is missing, fails, or prints no JSON, the call falls back to ``GenericRuntime``
(OpenAI-compatible API). Search and fetch always use the generic helpers, so they work
even without any LLM API key.

Safety/robustness rules (see docs/PLATFORMS.md for per-platform evidence):
* the CLI runs WITHOUT a shell, in an EMPTY temporary directory (agents scan their
  working directory; they must not see or edit the user's project);
* only commands with a known headless mode are probed by default. Editor launchers
  (``windsurf``, ``antigravity``) would open a GUI, so they are never run unless the
  user supplies an explicit ``<NAME>_CLI`` command;
* after ``max_cli_failures`` consecutive failures the CLI is skipped for the rest of
  the run (no 60 s timeout per call), going straight to the API fallback.

The ``<NAME>_CLI`` variable doubles as the auto-detection flag and as an optional
command override. The override is split with ``shlex`` and run without a shell; a value
that is not an executable (for example ``CODEX_CLI=1``) is ignored.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import threading
from typing import List, Optional, Tuple

from core.jsonparse import extract_json_object
from core.logs import get_logger

from .generic import GenericRuntime

_LOG = get_logger("runtime.cli")


def run_cli_json(cmd: List[str], prompt: str, schema: Optional[dict], *, prompt_mode: str = "stdin",
                 timeout: int = 60, tag: str = "cli") -> Optional[dict]:
    """Run one headless CLI call and return the JSON object it printed, else None.

    ``prompt_mode`` is ``"stdin"`` (prompt piped in) or ``"arg"`` (prompt appended as the
    last argument; stdin is closed)."""
    argv = list(cmd) + ([prompt] if prompt_mode == "arg" else [])
    try:
        with tempfile.TemporaryDirectory(prefix="deepdive-cli-") as workdir:
            proc = subprocess.run(
                argv, input=prompt if prompt_mode == "stdin" else None, text=True, capture_output=True,
                timeout=timeout, cwd=workdir,
                stdin=None if prompt_mode == "stdin" else subprocess.DEVNULL, errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        _LOG.warning(f"[{tag}] CLI invocation failed: {type(exc).__name__}")
        return None
    if proc.returncode != 0:
        _LOG.warning(f"[{tag}] CLI exited {proc.returncode}")
        return None
    result = extract_json_object((proc.stdout or "").strip() or (proc.stderr or "").strip(), schema)
    if result is None:
        _LOG.warning(f"[{tag}] CLI output contained no JSON")
    return result


class CliRuntime(GenericRuntime):
    """Base class: subclasses only declare data."""

    runtime_name: str = ""
    display_name: str = ""
    env_var: str = ""
    # Candidate commands in priority order; each is an argv prefix incl. the flags that put
    # the CLI in headless mode, e.g. ("codex", "exec", "-"). Empty = never probe a default.
    commands: Tuple[Tuple[str, ...], ...] = ()
    extra_paths: Tuple[str, ...] = ()
    prompt_mode: str = "stdin"      # "stdin" | "arg"
    cli_timeout: int = 60
    max_cli_failures: int = 3

    def __init__(self):
        super().__init__()
        self._override_ignored = ""
        self._cli_cmd: Optional[List[str]] = self._resolve_cli()
        self._failures = 0
        self._failure_lock = threading.Lock()

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
                return [found, *self.commands[0][1:]] if self.commands else [found]
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
        if not self.commands:
            _LOG.info(f"{tag} no headless agent CLI is known for {self.display_name}; using the generic API runtime "
                      f"(set {self.env_var} to a command that reads a prompt and prints JSON to override)")
        else:
            _LOG.warning(f"{tag} ⚠ No {self.display_name} CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        if not self._ready and not self.setup():
            return None
        if self._cli_cmd and self._failures < self.max_cli_failures:
            result = self._run_cli(prompt, schema)
            if result is not None:
                return result
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def _run_cli(self, prompt: str, schema: Optional[dict]) -> Optional[dict]:
        result = run_cli_json(self._cli_cmd, prompt, schema, prompt_mode=self.prompt_mode,
                              timeout=self.cli_timeout, tag=self.runtime_name)
        with self._failure_lock:
            self._failures = 0 if result is not None else self._failures + 1
            if self._failures == self.max_cli_failures:
                _LOG.warning(f"[{self.runtime_name}] CLI failed {self._failures}x in a row; "
                             "skipping it for the rest of this run (API fallback only)")
        return result


# Headless invocations. "verified" = flags confirmed against the installed CLI's --help and a
# live call (docs/PLATFORMS.md); "unverified" = taken from vendor docs, CLI not installed here.

class CodexRuntime(CliRuntime):
    # verified: `codex exec -` reads the prompt from stdin; read-only sandbox, no session files.
    runtime_name, display_name, env_var = "codex", "Codex", "CODEX_CLI"
    commands = (("codex", "exec", "-", "--skip-git-repo-check", "-s", "read-only", "--ephemeral",
                 "--color", "never"),)


class CursorRuntime(CliRuntime):
    # unverified: `cursor-agent -p "<prompt>"` print mode.
    runtime_name, display_name, env_var = "cursor", "Cursor Agent", "CURSOR_CLI"
    commands = (("cursor-agent", "-p", "--output-format", "text"),)
    prompt_mode = "arg"


class GeminiRuntime(CliRuntime):
    # verified: `-p` is headless mode and the text on stdin is appended to it.
    runtime_name, display_name, env_var = "gemini", "Gemini", "GEMINI_CLI"
    commands = (("gemini", "-p", "Follow the instructions given on stdin. Output only the requested JSON.",
                 "-o", "text"),)


class CopilotRuntime(CliRuntime):
    # unverified: standalone GitHub Copilot CLI `copilot -p "<prompt>"`. The old `gh copilot`
    # extension (suggest/explain) is not a scriptable agent and is not probed.
    runtime_name, display_name, env_var = "copilot", "Copilot", "COPILOT_CLI"
    commands = (("copilot", "-p"),)
    prompt_mode = "arg"


class AmazonQRuntime(CliRuntime):
    # unverified: `q chat --no-interactive "<prompt>"`.
    runtime_name, display_name, env_var = "amazon_q", "Amazon Q", "AMAZON_Q_CLI"
    commands = (("q", "chat", "--no-interactive"),)
    prompt_mode = "arg"


class WindsurfRuntime(CliRuntime):
    # `windsurf` is an editor launcher (it would open a GUI), not a headless agent: never probed.
    # Generic API unless WINDSURF_CLI names a real headless command.
    runtime_name, display_name, env_var = "windsurf", "Windsurf", "WINDSURF_CLI"


class KimiRuntime(CliRuntime):
    # verified: `kimi -p "<prompt>"` runs one prompt non-interactively (it appends a
    # "To resume this session" line, which JSON extraction ignores).
    runtime_name, display_name, env_var = "kimi", "Kimi", "KIMI_CLI"
    commands = (("kimi", "-p"),)
    extra_paths = ("~/.kimi-code/bin/kimi",)
    prompt_mode = "arg"


class GLMRuntime(CliRuntime):
    # No known standalone GLM/Z.ai headless agent CLI: generic API unless GLM_CLI is set.
    runtime_name, display_name, env_var = "glm", "GLM", "GLM_CLI"


class MiniMaxRuntime(CliRuntime):
    # No known standalone MiniMax headless agent CLI: generic API unless MINIMAX_CLI is set.
    runtime_name, display_name, env_var = "minimax", "MiniMax", "MINIMAX_CLI"


class AntigravityRuntime(CliRuntime):
    # Verified: the `antigravity` binary is a VS Code-style editor launcher (`antigravity -`
    # would open the piped text in an editor window). It is never probed by default.
    runtime_name, display_name, env_var = "antigravity", "Antigravity", "ANTIGRAVITY_CLI"
