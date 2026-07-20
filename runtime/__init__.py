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
    8. CURSOR_CLI
    9. GEMINI_CLI
    10. COPILOT_CLI
    11. AMAZON_Q_CLI
    12. WINDSURF_CLI
    13. KIMI_CLI
    14. GLM_CLI
    15. MINIMAX_CLI
    16. ANTIGRAVITY_CLI
    17. generic (fallback)
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
    if os.environ.get("CURSOR_CLI"):
        return "cursor"
    if os.environ.get("GEMINI_CLI"):
        return "gemini"
    if os.environ.get("COPILOT_CLI"):
        return "copilot"
    if os.environ.get("AMAZON_Q_CLI"):
        return "amazon_q"
    if os.environ.get("WINDSURF_CLI"):
        return "windsurf"
    if os.environ.get("KIMI_CLI"):
        return "kimi"
    if os.environ.get("GLM_CLI"):
        return "glm"
    if os.environ.get("MINIMAX_CLI"):
        return "minimax"
    if os.environ.get("ANTIGRAVITY_CLI"):
        return "antigravity"

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
    elif name == "cursor":
        from .cursor import CursorRuntime
        return CursorRuntime()
    elif name == "gemini":
        from .gemini import GeminiRuntime
        return GeminiRuntime()
    elif name == "copilot":
        from .copilot import CopilotRuntime
        return CopilotRuntime()
    elif name == "amazon_q":
        from .amazon_q import AmazonQRuntime
        return AmazonQRuntime()
    elif name == "windsurf":
        from .windsurf import WindsurfRuntime
        return WindsurfRuntime()
    elif name == "kimi":
        from .kimi import KimiRuntime
        return KimiRuntime()
    elif name == "glm":
        from .glm import GLMRuntime
        return GLMRuntime()
    elif name == "minimax":
        from .minimax import MiniMaxRuntime
        return MiniMaxRuntime()
    elif name == "antigravity":
        from .antigravity import AntigravityRuntime
        return AntigravityRuntime()
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
register("cursor", None)
register("gemini", None)
register("copilot", None)
register("amazon_q", None)
register("windsurf", None)
register("kimi", None)
register("glm", None)
register("minimax", None)
register("antigravity", None)

__all__ = ["BaseRuntime", "get_runtime", "detect", "register"]
