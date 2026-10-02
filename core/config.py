"""Explicit pipeline configuration (replaces import-time module globals + importlib.reload)."""

import os
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Optional

from core.tiers import DEFAULT_TIER, HARD_MAX_WORKERS, TIER_PRESETS

# option name -> environment variable. ``tier`` is a string, the rest positive integers.
OPTION_ENV: Dict[str, str] = {
    "tier": "DR_COST_TIER",
    "angles": "DR_ANGLES",
    "max_fetch": "DR_MAX_FETCH",
    "max_verify_claims": "DR_MAX_VERIFY_CLAIMS",
    "votes_per_claim": "DR_VOTES_PER_CLAIM",
    "refutations_required": "DR_REFUTATIONS_REQUIRED",
    "max_workers": "DR_MAX_WORKERS",
    "phase_budget_s": "DR_PHASE_BUDGET",
}
_INT_OPTIONS = tuple(name for name in OPTION_ENV if name != "tier")
DEFAULT_PHASE_BUDGET_S = 900


@dataclass(frozen=True)
class Config:
    """Immutable settings for one pipeline run. Pass it to ``engine.run(config=...)``."""

    tier: str = DEFAULT_TIER
    angles: int = TIER_PRESETS[DEFAULT_TIER]["angles"]
    max_fetch: int = TIER_PRESETS[DEFAULT_TIER]["max_fetch"]
    max_verify_claims: int = TIER_PRESETS[DEFAULT_TIER]["max_verify_claims"]
    votes_per_claim: int = TIER_PRESETS[DEFAULT_TIER]["votes_per_claim"]
    refutations_required: int = TIER_PRESETS[DEFAULT_TIER]["refutations_required"]
    max_workers: int = TIER_PRESETS[DEFAULT_TIER]["max_workers"]
    # Wall-clock budget per phase (seconds). A phase stops starting new work after it.
    phase_budget_s: int = DEFAULT_PHASE_BUDGET_S

    def __post_init__(self) -> None:
        if self.tier not in TIER_PRESETS:
            raise ValueError("tier must be one of: " + ", ".join(TIER_PRESETS) + ".")
        for name in _INT_OPTIONS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if self.refutations_required > self.votes_per_claim:
            raise ValueError("refutations_required cannot exceed votes_per_claim.")
        if self.max_workers > HARD_MAX_WORKERS:
            raise ValueError(f"max_workers cannot exceed the hard limit of {HARD_MAX_WORKERS}.")

    # ── constructors ──
    @classmethod
    def resolve(cls, overrides: Optional[Mapping[str, Any]] = None,
                environ: Optional[Mapping[str, str]] = None) -> "Config":
        """Strict: explicit overrides, then DR_* environment, then the tier preset.

        Any invalid value raises ``ValueError`` (used by the public harness API)."""
        overrides = dict(overrides or {})
        environ = os.environ if environ is None else environ
        unknown = set(overrides) - set(OPTION_ENV)
        if unknown:
            raise ValueError(f"Unsupported configuration option(s): {', '.join(sorted(unknown))}.")

        tier = str(overrides.get("tier", environ.get(OPTION_ENV["tier"], "")) or DEFAULT_TIER).strip().lower()
        if tier not in TIER_PRESETS:
            raise ValueError("tier must be one of: " + ", ".join(TIER_PRESETS) + ".")
        preset = dict(TIER_PRESETS[tier], phase_budget_s=DEFAULT_PHASE_BUDGET_S)
        values: Dict[str, Any] = {"tier": tier}
        for name in _INT_OPTIONS:
            values[name] = _strict_int(name, overrides.get(name, environ.get(OPTION_ENV[name], preset[name])))
        return cls(**values)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Config":
        """Lenient: invalid environment values fall back to the tier default instead of failing."""
        environ = os.environ if environ is None else environ
        tier = (environ.get(OPTION_ENV["tier"], "") or DEFAULT_TIER).strip().lower()
        tier = tier if tier in TIER_PRESETS else DEFAULT_TIER
        preset = dict(TIER_PRESETS[tier], phase_budget_s=DEFAULT_PHASE_BUDGET_S)
        values: Dict[str, Any] = {"tier": tier}
        for name in _INT_OPTIONS:
            try:
                values[name] = max(1, int(environ[OPTION_ENV[name]]))
            except (KeyError, TypeError, ValueError):
                values[name] = preset[name]
        values["refutations_required"] = min(values["refutations_required"], values["votes_per_claim"])
        values["max_workers"] = min(values["max_workers"], HARD_MAX_WORKERS)
        return cls(**values)

    def replace(self, **changes: Any) -> "Config":
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data.update(changes)
        return Config(**data)


def _strict_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if number < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return number
