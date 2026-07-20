"""Amazon Q Developer CLI runtime."""

import os
import shutil
import subprocess
from typing import Optional

from .generic import GenericRuntime
from ._cli_parallel import run_cli_parallel
from typing import Any, Callable, List


class AmazonQRuntime(GenericRuntime):
    """Runtime that prefers a local Amazon Q Developer `q` CLI when available."""

    def __init__(self):
        super().__init__()
        self._amazon_q_raw = os.environ.get("AMAZON_Q_CLI", "")
        self._amazon_q_path: Optional[str] = None
        self._amazon_q_use_shell = False
        if self._amazon_q_raw:
            if os.path.isabs(self._amazon_q_raw) and os.access(self._amazon_q_raw, os.X_OK):
                self._amazon_q_path = self._amazon_q_raw
            else:
                first = self._amazon_q_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._amazon_q_path = found
                    if len(self._amazon_q_raw.split()) > 1:
                        self._amazon_q_use_shell = True
                else:
                    self._amazon_q_use_shell = True

        if not self._amazon_q_path:
            self._amazon_q_path = shutil.which("q")

    @property
    def name(self) -> str:
        return "amazon_q"

    def setup(self) -> bool:
        """Prepare the local Amazon Q CLI or the generic fallback runtime."""
        if self._amazon_q_path:
            self._ready = True
            print(f"[amazon_q] ✅ Amazon Q CLI detected at {self._amazon_q_path}")
            if self._amazon_q_raw and self._amazon_q_use_shell:
                print(f"[amazon_q] ⚠ Using shell invocation for AMAZON_Q_CLI: {self._amazon_q_raw}")
            return True

        print("[amazon_q] ⚠ No Amazon Q CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call Amazon Q CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, "_ready", False) and not self.setup():
            return None

        if self._amazon_q_path:
            try:
                if self._amazon_q_raw and self._amazon_q_use_shell:
                    proc = subprocess.run(
                        self._amazon_q_raw, input=prompt, text=True, capture_output=True,
                        shell=True, timeout=60,
                    )
                else:
                    proc = subprocess.run(
                        [self._amazon_q_path], input=prompt, text=True, capture_output=True,
                        shell=False, timeout=60,
                    )

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[amazon_q] CLI exited {proc.returncode}; falling back to generic")
                else:
                    result = self._extract_json(out, schema)
                    if result is not None:
                        return result
                    print("[amazon_q] CLI output contained no JSON; falling back to generic")
            except Exception as exc:
                print(f"[amazon_q] CLI invocation failed: {exc}; falling back to generic")

        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        if self._amazon_q_path:
            return run_cli_parallel(fn_list, max_workers)
        return super().run_parallel(fn_list, max_workers)
