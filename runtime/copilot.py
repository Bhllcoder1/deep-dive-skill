"""
GitHub Copilot Agent CLI Runtime.
GitHub Copilot CLI için runtime.
Terminal + file ops var, web search yok -> generic fallback.
"""

from .generic import GenericRuntime
import os
import shutil
import subprocess
from typing import Optional


class CopilotRuntime(GenericRuntime):
    """Copilot runtime that prefers a local CLI when available.

    Behavior:
    - If `COPILOT_CLI` env var points to an executable (or a command in PATH), use it.
    - Else if a standalone `copilot` binary exists in PATH, use that.
    - Else if `gh` exists in PATH, use its `copilot` subcommand.
    - If no CLI is available, fall back to `GenericRuntime` (DeepSeek API).

    The CLI is invoked with the prompt on stdin and its stdout is parsed
    for JSON (using GenericRuntime's extractor). If the CLI call fails
    or returns non-JSON, we gracefully fall back to the generic API.
    """

    def __init__(self):
        super().__init__()
        self._copilot_raw = os.environ.get("COPILOT_CLI", "")
        self._copilot_path: Optional[str] = None
        self._copilot_args: list[str] = []
        self._copilot_use_shell: bool = False
        # Resolve CLI: explicit path, PATH lookup, or leave None
        if self._copilot_raw:
            # If COPILOT_CLI is an absolute/relative path to an executable
            if os.path.isabs(self._copilot_raw) and os.access(self._copilot_raw, os.X_OK):
                self._copilot_path = self._copilot_raw
            else:
                # Try PATH lookup for the first token
                first = self._copilot_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._copilot_path = found
                    # If user provided extra args in COPILOT_CLI, use shell invocation
                    if len(self._copilot_raw.split()) > 1:
                        self._copilot_use_shell = True
                else:
                    # Could be a shell command string; try to use as-is with shell
                    self._copilot_use_shell = True

        if not self._copilot_path:
            self._copilot_path = shutil.which("copilot")
            if not self._copilot_path:
                self._copilot_path = shutil.which("gh")
                if self._copilot_path:
                    self._copilot_args = ["copilot"]

    @property
    def name(self) -> str:
        return "copilot"

    def setup(self) -> bool:
        """Prepare runtime. Prefer local Copilot CLI, otherwise fall back to GenericRuntime.setup()."""
        if self._copilot_path:
            self._ready = True
            print(f"[copilot] ✅ Copilot CLI detected at {self._copilot_path}")
            if self._copilot_raw and self._copilot_use_shell:
                print(f"[copilot] ⚠ Using shell invocation for COPILOT_CLI: {self._copilot_raw}")
            return True

        # No CLI — fall back to GenericRuntime (which requires DEEPSEEK_API_KEY)
        print("[copilot] ⚠ No Copilot CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Copilot CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, '_ready', False):
            if not self.setup():
                return None

        # If we have a CLI, try it first
        if self._copilot_path:
            try:
                if self._copilot_raw and self._copilot_use_shell:
                    # Use the raw command string (may include args)
                    proc = subprocess.run(self._copilot_raw, input=prompt, text=True,
                                          capture_output=True, shell=True, timeout=60)
                else:
                    proc = subprocess.run([self._copilot_path, *self._copilot_args],
                                          input=prompt, text=True, capture_output=True,
                                          shell=False, timeout=60)

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[copilot] CLI exited {proc.returncode}; falling back to generic")
                else:
                    # Try to extract JSON from CLI output
                    res = self._extract_json(out, schema)
                    if res is not None:
                        return res
                    print("[copilot] CLI output contained no JSON; falling back to generic")
            except Exception as e:
                print(f"[copilot] CLI invocation failed: {e}; falling back to generic")

        # Fallback to GenericRuntime (DeepSeek API)
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)
