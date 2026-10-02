"""
Runtime adapter registry.

Every platform adapter is registered here by name. ``get_runtime`` and the harness
read this registry, so adding an adapter means one ``register()`` call (or one entry
in ``_BUILTIN``); nothing else needs to change.

    from runtime import get_runtime, register
    rt = get_runtime()            # auto-detect (DR_RUNTIME, then *_CLI flags)
    rt = get_runtime("hermes")    # forced

    register("mine", MyRuntime)                      # a class
    register("mine", "my_pkg.my_mod:MyRuntime")      # or a lazy "module:Class" path
    # optional auto-detection: register("mine", MyRuntime, detect_env="MINE_CLI")
"""

import importlib
import os
from typing import Dict, List, Optional, Tuple, Type, Union

from core.logs import get_logger

from .base import BaseRuntime

RuntimeTarget = Union[Type[BaseRuntime], str]

_RUNTIME_REGISTRY: Dict[str, RuntimeTarget] = {}
# (environment variable, runtime name) in detection priority order.
_DETECTION: List[Tuple[str, str]] = []
# Flags that only count when exactly "1" (other values such as "0" mean off).
_STRICT_ONE = {"CLAUDE_CODE", "CLAUDECODE"}


def register(name: str, runtime: RuntimeTarget, detect_env: Optional[str] = None) -> None:
    """Register a runtime class, or a lazily imported ``"module:Class"`` path."""
    if not isinstance(name, str) or not name.strip() or name == "auto":
        raise ValueError("runtime name must be a non-empty string other than 'auto'")
    if not (isinstance(runtime, str) or (isinstance(runtime, type) and issubclass(runtime, BaseRuntime))):
        raise TypeError("runtime must be a BaseRuntime subclass or a 'module:Class' string")
    _RUNTIME_REGISTRY[name] = runtime
    if detect_env:
        _DETECTION[:] = [pair for pair in _DETECTION if pair[1] != name] + [(detect_env, name)]


def registered_names() -> List[str]:
    return sorted(_RUNTIME_REGISTRY)


def detect() -> str:
    """Pick a runtime: ``DR_RUNTIME`` if set, else the first registered detection flag
    present in the environment, else ``generic``. ``CLAUDE_CODE`` must equal ``"1"``."""
    force = os.environ.get("DR_RUNTIME", "auto")
    if force and force != "auto":
        return force
    for env_var, name in _DETECTION:
        value = os.environ.get(env_var)
        if value == "1" if env_var in _STRICT_ONE else value:
            return name
    return "generic"


def _load(target: RuntimeTarget) -> Type[BaseRuntime]:
    if isinstance(target, str):
        module_name, _, class_name = target.partition(":")
        return getattr(importlib.import_module(module_name), class_name)
    return target


def get_runtime(runtime_name: Optional[str] = None) -> BaseRuntime:
    """Return an instance of the requested runtime (None = auto-detect).

    Unknown names fall back to the generic runtime."""
    name = runtime_name or detect()
    target = _RUNTIME_REGISTRY.get(name)
    if target is None:
        get_logger("runtime").warning(
            f"Unknown runtime {name!r} (registered: {', '.join(registered_names())}); using 'generic'.")
        target = _RUNTIME_REGISTRY["generic"]
    return _load(target)()


_BUILTIN = [
    # name, target, detection env var (priority order = list order)
    ("hermes", "runtime.hermes:HermesRuntime", "HERMES_AGENT"),
    ("claude_code", "runtime.claude_code:ClaudeCodeRuntime", "CLAUDE_CODE"),
    ("aider", "runtime.aider:AiderRuntime", "AIDER_CHAT_MODE"),
    ("codex", "runtime.cli:CodexRuntime", "CODEX_CLI"),
    ("cline", "runtime.cline:ClineRuntime", "CLINE_MCP"),
    ("cursor", "runtime.cli:CursorRuntime", "CURSOR_CLI"),
    ("gemini", "runtime.cli:GeminiRuntime", "GEMINI_CLI"),
    ("copilot", "runtime.cli:CopilotRuntime", "COPILOT_CLI"),
    ("amazon_q", "runtime.cli:AmazonQRuntime", "AMAZON_Q_CLI"),
    ("windsurf", "runtime.cli:WindsurfRuntime", "WINDSURF_CLI"),
    ("kimi", "runtime.cli:KimiRuntime", "KIMI_CLI"),
    ("glm", "runtime.cli:GLMRuntime", "GLM_CLI"),
    ("minimax", "runtime.cli:MiniMaxRuntime", "MINIMAX_CLI"),
    ("antigravity", "runtime.cli:AntigravityRuntime", "ANTIGRAVITY_CLI"),
    ("generic", "runtime.generic:GenericRuntime", None),
]
for _name, _target, _flag in _BUILTIN:
    register(_name, _target, _flag)
# Extra detection flags for the same adapters, inserted right after their primary flag.
# CLAUDECODE=1 is what the real Claude Code sets (CLAUDE_CODE=1 is this project's own
# convention); CLAUDE_CODE_ENTRYPOINT is also set by Claude Code sessions.
for _primary, _extra in (("AIDER_CHAT_MODE", "AIDER_VERSION"), ("CLAUDE_CODE", "CLAUDECODE"),
                         ("CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")):
    _name = dict(_DETECTION)[_primary]
    _DETECTION.insert(_DETECTION.index((_primary, _name)) + 1, (_extra, _name))

__all__ = ["BaseRuntime", "get_runtime", "detect", "register", "registered_names"]
