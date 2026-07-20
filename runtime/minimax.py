"""
MiniMax Code CLI Runtime.
MiniMax Code CLI için runtime.
Terminal + file ops var, web search yok -> generic fallback.
"""

from .generic import GenericRuntime
import os
import shutil
import subprocess
from typing import Optional


class MiniMaxRuntime(GenericRuntime):
    """MiniMax runtime that prefers a local `minimax` CLI when available.

    Behavior:
    - If `MINIMAX_CLI` env var points to an executable (or a command in PATH), use it.
    - Else if a `minimax` binary exists in PATH, use that.
    - If no CLI is available, fall back to `GenericRuntime` (DeepSeek API).

    The CLI is invoked with the prompt on stdin and its stdout is parsed
    for JSON (using GenericRuntime's extractor). If the CLI call fails
    or returns non-JSON, we gracefully fall back to the generic API.
    """

    def __init__(self):
        super().__init__()
        self._minimax_raw = os.environ.get("MINIMAX_CLI", "")
        self._minimax_path: Optional[str] = None
        self._minimax_use_shell: bool = False
        # Resolve CLI: explicit path, PATH lookup, or leave None
        if self._minimax_raw:
            # If MINIMAX_CLI is an absolute/relative path to an executable
            if os.path.isabs(self._minimax_raw) and os.access(self._minimax_raw, os.X_OK):
                self._minimax_path = self._minimax_raw
            else:
                # Try PATH lookup for the first token
                first = self._minimax_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._minimax_path = found
                    # If user provided extra args in MINIMAX_CLI, use shell invocation
                    if len(self._minimax_raw.split()) > 1:
                        self._minimax_use_shell = True
                else:
                    # Could be a shell command string; try to use as-is with shell
                    self._minimax_use_shell = True

        if not self._minimax_path:
            self._minimax_path = shutil.which("minimax")

    @property
    def name(self) -> str:
        return "minimax"

    def setup(self) -> bool:
        """Prepare runtime. Prefer local MiniMax CLI, otherwise fall back to GenericRuntime.setup()."""
        if self._minimax_path:
            self._ready = True
            print(f"[minimax] ✅ MiniMax CLI detected at {self._minimax_path}")
            if self._minimax_raw and self._minimax_use_shell:
                print(f"[minimax] ⚠ Using shell invocation for MINIMAX_CLI: {self._minimax_raw}")
            return True

        # No CLI — fall back to GenericRuntime (which requires DEEPSEEK_API_KEY)
        print("[minimax] ⚠ No MiniMax CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call MiniMax CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, '_ready', False):
            if not self.setup():
                return None

        # If we have a CLI, try it first
        if self._minimax_path:
            cmd = None
            try:
                if self._minimax_raw and self._minimax_use_shell:
                    # Use the raw command string (may include args)
                    cmd = self._minimax_raw
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                          capture_output=True, shell=True, timeout=60)
                else:
                    cmd = [self._minimax_path]
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                          capture_output=True, shell=False, timeout=60)

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[minimax] CLI exited {proc.returncode}; falling back to generic")
                else:
                    # Try to extract JSON from CLI output
                    res = self._extract_json(out, schema)
                    if res is not None:
                        return res
                    print("[minimax] CLI output contained no JSON; falling back to generic")
            except Exception as e:
                print(f"[minimax] CLI invocation failed: {e}; falling back to generic")

        # Fallback to GenericRuntime (DeepSeek API)
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)
