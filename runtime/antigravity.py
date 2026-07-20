"""Google Antigravity CLI runtime."""

import os
import shutil
import subprocess
from typing import Any, Callable, List, Optional

from ._cli_parallel import run_cli_parallel
from .generic import GenericRuntime


class AntigravityRuntime(GenericRuntime):
    """Runtime that prefers Google's local ``antigravity`` CLI when available."""

    def __init__(self):
        super().__init__()
        self._antigravity_raw = os.environ.get("ANTIGRAVITY_CLI", "")
        self._antigravity_path: Optional[str] = None
        self._antigravity_use_shell = False
        if self._antigravity_raw:
            if os.path.isabs(self._antigravity_raw) and os.access(self._antigravity_raw, os.X_OK):
                self._antigravity_path = self._antigravity_raw
            else:
                first = self._antigravity_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._antigravity_path = found
                    if len(self._antigravity_raw.split()) > 1:
                        self._antigravity_use_shell = True
                else:
                    self._antigravity_use_shell = True

        if not self._antigravity_path:
            self._antigravity_path = shutil.which("antigravity")

    @property
    def name(self) -> str:
        return "antigravity"

    def setup(self) -> bool:
        """Prepare runtime, preferring the local Antigravity CLI."""
        if self._antigravity_path:
            self._ready = True
            print(f"[antigravity] ✅ Antigravity CLI detected at {self._antigravity_path}")
            if self._antigravity_raw and self._antigravity_use_shell:
                print(f"[antigravity] ⚠ Using shell invocation for ANTIGRAVITY_CLI: {self._antigravity_raw}")
            return True

        print("[antigravity] ⚠ No Antigravity CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Antigravity CLI if available, else delegate to GenericRuntime."""
        if not getattr(self, "_ready", False) and not self.setup():
            return None

        if self._antigravity_path:
            try:
                if self._antigravity_raw and self._antigravity_use_shell:
                    proc = subprocess.run(
                        self._antigravity_raw, input=prompt, text=True, capture_output=True,
                        shell=True, timeout=60,
                    )
                else:
                    proc = subprocess.run(
                        [self._antigravity_path], input=prompt, text=True, capture_output=True,
                        shell=False, timeout=60,
                    )
                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()
                if proc.returncode != 0:
                    print(f"[antigravity] CLI exited {proc.returncode}; falling back to generic")
                else:
                    result = self._extract_json(out, schema)
                    if result is not None:
                        return result
                    print("[antigravity] CLI output contained no JSON; falling back to generic")
            except Exception as exc:
                print(f"[antigravity] CLI invocation failed: {exc}; falling back to generic")

        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        # Native multi-agent orchestration is exposed only through /agent and /agents
        # in the interactive TUI, not a scriptable API reachable by piping one prompt
        # to stdin and reading one output.
        if self._antigravity_path:
            return run_cli_parallel(fn_list, max_workers)
        return super().run_parallel(fn_list, max_workers)
