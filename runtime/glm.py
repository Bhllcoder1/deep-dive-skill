"""
GLM Code CLI Runtime.
Z.ai / Zhipu AI's coding CLI için runtime.
Terminal + file ops var, web search yok -> generic fallback.
"""

from .generic import GenericRuntime
from ._cli_parallel import run_cli_parallel
import os
import shutil
import subprocess
from typing import Any, Callable, List, Optional


class GLMRuntime(GenericRuntime):
    """GLM runtime that prefers a local `glm` or `zai` CLI when available.

    Behavior:
    - If `GLM_CLI` env var points to an executable (or a command in PATH), use it.
    - Else if a `glm` or `zai` binary exists in PATH, use that.
    - If no CLI is available, fall back to `GenericRuntime` (DeepSeek API).

    The CLI is invoked with the prompt on stdin and its stdout is parsed
    for JSON (using GenericRuntime's extractor). If the CLI call fails
    or returns non-JSON, we gracefully fall back to the generic API.
    """

    def __init__(self):
        super().__init__()
        self._glm_raw = os.environ.get("GLM_CLI", "")
        self._glm_path: Optional[str] = None
        self._glm_use_shell: bool = False
        # Resolve CLI: explicit path, PATH lookup, or leave None
        if self._glm_raw:
            # If GLM_CLI is an absolute/relative path to an executable
            if os.path.isabs(self._glm_raw) and os.access(self._glm_raw, os.X_OK):
                self._glm_path = self._glm_raw
            else:
                # Try PATH lookup for the first token
                first = self._glm_raw.split()[0]
                found = shutil.which(first)
                if found:
                    self._glm_path = found
                    # If user provided extra args in GLM_CLI, use shell invocation
                    if len(self._glm_raw.split()) > 1:
                        self._glm_use_shell = True
                else:
                    # Could be a shell command string; try to use as-is with shell
                    self._glm_use_shell = True

        if not self._glm_path:
            self._glm_path = shutil.which("glm") or shutil.which("zai")

    @property
    def name(self) -> str:
        return "glm"

    def setup(self) -> bool:
        """Prepare runtime. Prefer local GLM CLI, otherwise fall back to GenericRuntime.setup()."""
        if self._glm_path:
            self._ready = True
            print(f"[glm] ✅ GLM CLI detected at {self._glm_path}")
            if self._glm_raw and self._glm_use_shell:
                print(f"[glm] ⚠ Using shell invocation for GLM_CLI: {self._glm_raw}")
            return True

        # No CLI — fall back to GenericRuntime (which requires DEEPSEEK_API_KEY)
        print("[glm] ⚠ No GLM CLI found; falling back to generic runtime (DeepSeek API)")
        return super().setup()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """Call GLM CLI if available, else delegate to GenericRuntime.agent_call()."""
        if not getattr(self, '_ready', False):
            if not self.setup():
                return None

        # If we have a CLI, try it first
        if self._glm_path:
            try:
                if self._glm_raw and self._glm_use_shell:
                    # Use the raw command string (may include args)
                    proc = subprocess.run(
                        self._glm_raw, input=prompt, text=True, capture_output=True,
                        shell=True, timeout=60,
                    )
                else:
                    proc = subprocess.run(
                        [self._glm_path], input=prompt, text=True, capture_output=True,
                        shell=False, timeout=60,
                    )

                out = (proc.stdout or "").strip()
                if not out and proc.stderr:
                    out = proc.stderr.strip()

                if proc.returncode != 0:
                    print(f"[glm] CLI exited {proc.returncode}; falling back to generic")
                else:
                    # Try to extract JSON from CLI output
                    res = self._extract_json(out, schema)
                    if res is not None:
                        return res
                    print("[glm] CLI output contained no JSON; falling back to generic")
            except Exception as e:
                print(f"[glm] CLI invocation failed: {e}; falling back to generic")

        # Fallback to GenericRuntime (DeepSeek API)
        return super().agent_call(prompt, schema=schema, label=label, phase=phase)

    def run_parallel(self, fn_list: List[Callable[[], Any]], max_workers: int = 3) -> List[Any]:
        if self._glm_path:
            return run_cli_parallel(fn_list, max_workers)
        return super().run_parallel(fn_list, max_workers)
