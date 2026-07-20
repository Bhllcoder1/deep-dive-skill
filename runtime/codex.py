"""
Codex CLI Runtime.
OpenAI Codex CLI için runtime.
Terminal + file ops var, web search yok -> generic fallback.
"""

from .generic import GenericRuntime


class CodexRuntime(GenericRuntime):
    @property
    def name(self) -> str:
        return "codex"
