"""
Kimi Code CLI Runtime.
Moonshot AI Kimi Code için runtime.
Terminal + file ops var, web search yok -> generic fallback.
"""

from .generic import GenericRuntime
from ._cli_parallel import run_cli_parallel
import os
import shutil
import subprocess
from typing import Any, Callable, List, Optional


class KimiRuntime(GenericRuntime):
    """Kimi runtime that prefers a local `kimi` CLI when available.

    Behavior:
    - If `KIMI_CLI` env var points to an executable (or a command in PATH), use it.
    - Else if a `kimi` binary exists in PATH, use that.
    - Else if the standard Kimi Code install path is executable, use that.
    - If no CLI is available, fall back to `GenericRuntime` (DeepSeek API).

    The CLI is invoked with the prompt on stdin and its stdout is parsed
    for JSON (using GenericRuntime's extractor). If the CLI call fails
    or returns non-JSON, we gracefully fall back to the generic API.
    """

    def __init__(self):
        super().__init__()
        self._kimi_raw = os.environ.get("KIMI_CLI", "")
        self._kimi_path: Optional[str] = None
        self._kimi_use_shell: bool = False
        # Resolve CLI: explicit path, PATH lookup, standard install path, or leave None
        if self._kimi_raw:
            # If KIMI_CLI is an absolute/relative path to an executable
            if os.path.isabs(self._kimi_raw) and os.access(self._kimi_raw, os.X_OK):
                self._kimi_path = self._kimi_raw
            else:
                # Try PATH lookup for the first token
                first = self._kimi_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._kimi_path = found
                    # If user provided extra args in KIMI_CLI, use shell invocation
                    if len(self._kimi_raw.split()) > 1:
                        self._kimi_use_shell = True
                else:
                    # Could be a shell command string; try to use as-is with shell
                    self._kimi_use_shell = True

        if not self._kimi_path:
            self._kimi_path = shutil.which("kimi")

        if not self._kimi_path:
            kimi_home_path = os.path.expanduser("~/.kimi-code/bin/kimi")
            if os.path.isfile(kimi_home_path) and os.access(kimi_home_path, os.X_OK):
                self._kimi_path = kimi_home_path

    @property
    def name(self) -> str:
        return "kimi"

    def setup(self) -> bool:
        """Prepare runtime. Prefer local Kimi CLI, otherwise fall back to GenericRuntime.setup()."""
        if self._kimi_path:
            self._ready = True
            print(f"[kimi] ✅ Kimi CLI detected at {self._kimi_path}")
            if self._kimi_raw and self._kimi_use_shell:
                print(f"[kimi] ⚠ Using shell invocation for KIMI_CLI: {self._kimi_raw}")
            return True

        # No CLI — fall back to GenericRuntime (which requires DEEPSEEK_API_KEY)
        print("[kimi] ⚠ No Kimi CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Kimi CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, '_ready', False):
            if not self.setup():
                return None

        # If we have a CLI, try it first
        if self._kimi_path:
            cmd = None
            try:
                if self._kimi_raw and self._kimi_use_shell:
                    # Use the raw command string (may include args)
                    cmd = self._kimi_raw
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                          capture_output=True, shell=True, timeout=60)
                else:
                    cmd = [self._kimi_path]
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                          capture_output=True, shell=False, timeout=60)

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[kimi] CLI exited {proc.returncode}; falling back to generic")
                else:
                    # Try to extract JSON from CLI output
                    res = self._extract_json(out, schema)
                    if res is not None:
                        return res
                    print("[kimi] CLI output contained no JSON; falling back to generic")
            except Exception as e:
                print(f"[kimi] CLI invocation failed: {e}; falling back to generic")

        # Fallback to GenericRuntime (DeepSeek API)
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        if self._kimi_path:
            return run_cli_parallel(fn_list, max_workers)
        return super().run_parallel(fn_list, max_workers)
