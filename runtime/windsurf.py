"""
Windsurf CLI Runtime.
Windsurf için runtime.
CLI varsa kullanır, yoksa generic fallback.
"""

from .generic import GenericRuntime
from ._cli_parallel import run_cli_parallel
import os
import shutil
import subprocess
from typing import Any, Callable, List, Optional


class WindsurfRuntime(GenericRuntime):
    """Windsurf runtime that prefers a local `windsurf` CLI when available.

    Behavior:
    - If `WINDSURF_CLI` env var points to an executable (or a command in PATH), use it.
    - Else if a `windsurf` binary exists in PATH, use that.
    - If no CLI is available, fall back to `GenericRuntime` (DeepSeek API).

    The CLI is invoked with the prompt on stdin and its stdout is parsed
    for JSON (using GenericRuntime's extractor). If the CLI call fails
    or returns non-JSON, we gracefully fall back to the generic API.
    """

    def __init__(self):
        super().__init__()
        self._windsurf_raw = os.environ.get("WINDSURF_CLI", "")
        self._windsurf_path: Optional[str] = None
        self._windsurf_use_shell: bool = False
        # Resolve CLI: explicit path, PATH lookup, or leave None
        if self._windsurf_raw:
            # If WINDSURF_CLI is an absolute/relative path to an executable
            if os.path.isabs(self._windsurf_raw) and os.access(self._windsurf_raw, os.X_OK):
                self._windsurf_path = self._windsurf_raw
            else:
                # Try PATH lookup for the first token
                first = self._windsurf_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._windsurf_path = found
                    # If user provided extra args in WINDSURF_CLI, use shell invocation
                    if len(self._windsurf_raw.split()) > 1:
                        self._windsurf_use_shell = True
                else:
                    # Could be a shell command string; try to use as-is with shell
                    self._windsurf_use_shell = True

        if not self._windsurf_path:
            self._windsurf_path = shutil.which("windsurf")

    @property
    def name(self) -> str:
        return "windsurf"

    def setup(self) -> bool:
        """Prepare runtime. Prefer local Windsurf CLI, otherwise fall back to GenericRuntime.setup()."""
        if self._windsurf_path:
            self._ready = True
            print(f"[windsurf] ✅ Windsurf CLI detected at {self._windsurf_path}")
            if self._windsurf_raw and self._windsurf_use_shell:
                print(f"[windsurf] ⚠ Using shell invocation for WINDSURF_CLI: {self._windsurf_raw}")
            return True

        # No stable public CLI — fall back to GenericRuntime (which requires DEEPSEEK_API_KEY)
        print("[windsurf] ⚠ Windsurf CLI wasn't found; using the generic API path")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Windsurf CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, '_ready', False):
            if not self.setup():
                return None

        # If we have a CLI, try it first
        if self._windsurf_path:
            cmd = None
            try:
                if self._windsurf_raw and self._windsurf_use_shell:
                    # Use the raw command string (may include args)
                    cmd = self._windsurf_raw
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                           capture_output=True, shell=True, timeout=60)
                else:
                    cmd = [self._windsurf_path]
                    proc = subprocess.run(cmd, input=prompt, text=True,
                                           capture_output=True, shell=False, timeout=60)

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[windsurf] CLI exited {proc.returncode}; falling back to generic")
                else:
                    # Try to extract JSON from CLI output
                    res = self._extract_json(out, schema)
                    if res is not None:
                        return res
                    print("[windsurf] CLI output contained no JSON; falling back to generic")
            except Exception as e:
                print(f"[windsurf] CLI invocation failed: {e}; falling back to generic")

        # Fallback to GenericRuntime (DeepSeek API)
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        if self._windsurf_path:
            return run_cli_parallel(fn_list, max_workers)
        return super().run_parallel(fn_list, max_workers)
