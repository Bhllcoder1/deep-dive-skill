"""
Deep Dive Skill — Core engine.
Universal pipeline: Scope → Search → Fetch → Verify → Synthesize.
Works on any platform (Hermes, Claude Code, Aider, Codex, etc.)

Public names are resolved lazily (PEP 562) so that low-level modules such as
``core.logs`` / ``core.jsonparse`` can be imported by ``runtime`` without pulling in the
engine (which itself imports ``runtime``).
"""

from importlib import import_module

_LAZY = {
    "deep_research": ("core.engine", "run"),
    "PipelineMonitor": ("core.monitor", "PipelineMonitor"),
    "ModelConfig": ("core.monitor", "ModelConfig"),
    "AgentStatus": ("core.monitor", "AgentStatus"),
    "PhaseStatus": ("core.monitor", "PhaseStatus"),
    "AgentRecord": ("core.monitor", "AgentRecord"),
    "PhaseRecord": ("core.monitor", "PhaseRecord"),
}

__all__ = sorted(_LAZY)


def __getattr__(name):
    try:
        module, attribute = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module 'core' has no attribute {name!r}") from None
    return getattr(import_module(module), attribute)
