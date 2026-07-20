"""
Aider Runtime.
Aider'ın gücü: chat mode, file editing, terminal.
Kendi web search tool'u yok -> generic fallback kullanır.
Özel: --model ile farklı LLM kullanabilir.
"""

from .generic import GenericRuntime


class AiderRuntime(GenericRuntime):
    """Aider için runtime. Generic ile aynı, sadece isim farklı."""

    @property
    def name(self) -> str:
        return "aider"

    def setup(self) -> bool:
        result = super().setup()
        if result:
            print("[aider] ⚠ Web araması için DDG scraping kullanılacak (built-in web search yok)")
        return result
