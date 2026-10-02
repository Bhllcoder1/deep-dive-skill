"""Mutable data flowing through the phases of one run."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RunState:
    question: str
    angles: List[Dict[str, str]] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)        # Search output
    dupes: List[Dict[str, Any]] = field(default_factory=list)
    search_fallbacks: int = 0
    fetched: List[Dict[str, Any]] = field(default_factory=list)        # Fetch output
    all_claims: List[Dict[str, Any]] = field(default_factory=list)
    ranked_claims: List[Dict[str, Any]] = field(default_factory=list)  # claims chosen for Verify
    voted: List[Dict[str, Any]] = field(default_factory=list)
    confirmed: List[Dict[str, Any]] = field(default_factory=list)
    killed: List[Dict[str, Any]] = field(default_factory=list)
    unverified: List[Dict[str, Any]] = field(default_factory=list)
    # A phase sets this to end the run (success, partial result or error).
    result: Optional[Dict[str, Any]] = None
