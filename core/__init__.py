"""
Deep Dive Skill — Core engine.
Universal pipeline: Scope → Search → Fetch → Verify → Synthesize.
Works on any platform (Hermes, Claude Code, Aider, Codex, etc.)
"""

from .engine import run as deep_research
from .monitor import PipelineMonitor, ModelConfig, AgentStatus, PhaseStatus
from .monitor import AgentRecord, PhaseRecord

__all__ = [
    "deep_research",
    "PipelineMonitor", "ModelConfig",
    "AgentStatus", "PhaseStatus",
    "AgentRecord", "PhaseRecord",
]
