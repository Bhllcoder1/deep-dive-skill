"""
Runtime Adapter Factory.
Her platform için doğru runtime'ı seçer ve yapılandırır.

Kullanım:
    from runtime import get_runtime
    
    # Otomatik algılama
    rt = get_runtime()
    rt.setup()
    
    # Zorla seçim
    rt = get_runtime("hermes")
    rt = get_runtime("claude_code")
    rt = get_runtime("generic")
    
    # Runtime'ı kullan
    result = rt.agent_call("prompt", schema)
    results = rt.web_search("query")
    parallel_results = rt.run_parallel([fn1, fn2, fn3])
"""

import os
from typing import Optional

from .base import BaseRuntime


def detect() -> str:
    """
    Platformu otomatik algılar.
    
    Sırasıyla:
    1. DR_RUNTIME environment variable (force)
    2. HERMES_AGENT
    3. CLAUDE_CODE
    4. AIDER_CHAT_MODE / AIDER_VERSION
    5. OPENCLAW_MODE
    6. CODEX_CLI
    7. CLINE_MCP
    8. generic (fallback)
    """
    force = os.environ.get("DR_RUNTIME", "auto")
    if force and force != "auto":
        return force

    if os.environ.get("HERMES_AGENT"):
        return "hermes"
    if os.environ.get("CLAUDE_CODE") == "1":
        return "claude_code"
    if os.environ.get("AIDER_CHAT_MODE") or os.environ.get("AIDER_VERSION"):
        return "aider"
    if os.environ.get("OPENCLAW_MODE"):
        return "openclaw"
    if os.environ.get("CODEX_CLI"):
        return "codex"
    if os.environ.get("CLINE_MCP"):
        return "cline"

    return "generic"


# Runtime sınıfı kaydı
_RUNTIME_REGISTRY = {}


def register(name: str, runtime_class):
    """Bir runtime sınıfını kaydeder."""
    _RUNTIME_REGISTRY[name] = runtime_class


def get_runtime(runtime_name: Optional[str] = None) -> BaseRuntime:
    """
    İstenen runtime'ı döndürür.
    
    Args:
        runtime_name: Runtime adı (hermes, claude_code, generic, vb.)
                      None = otomatik algıla
    
    Returns:
        BaseRuntime türevi bir örnek
    """
    name = runtime_name or detect()

    # Lazy import — sadece ihtiyaç duyulan runtime yüklenir
    if name == "hermes":
        from .hermes import HermesRuntime
        return HermesRuntime()
    elif name == "claude_code":
        from .claude_code import ClaudeCodeRuntime
        return ClaudeCodeRuntime()
    elif name == "aider":
        from .aider import AiderRuntime
        return AiderRuntime()
    elif name == "codex":
        from .codex import CodexRuntime
        return CodexRuntime()
    elif name == "cline":
        from .cline import ClineRuntime
        return ClineRuntime()
    else:
        from .generic import GenericRuntime
        return GenericRuntime()


# Built-in runtime'ları kaydet
register("hermes", None)  # Lazy loaded
register("claude_code", None)
register("generic", None)
register("aider", None)
register("codex", None)
register("cline", None)

__all__ = ["BaseRuntime", "get_runtime", "detect", "register"]
