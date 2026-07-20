"""
Cost tiers — bound how many agent calls a single research run can spawn.

Total agent calls ≈ 2 (scope + synthesize) + angles + max_fetch + (max_verify_claims × votes_per_claim)
  angles            → Scope: how many parallel search angles get generated
  max_fetch         → Search/Fetch: how many URLs get fetched + claim-extracted
  max_verify_claims → Verify: how many claims get adversarially checked
  votes_per_claim   → Verify: independent verifiers per claim

max_workers bounds how many of those calls may run CONCURRENTLY at once — this is the
actual "don't spawn 200 agents simultaneously" knob, independent of the total budget above.
"""

from typing import Dict

TIER_PRESETS: Dict[str, Dict[str, int]] = {
    # ~8 agent calls — sanity check / cheap fact lookup, single-vote verification
    "low": {
        "angles": 2, "max_fetch": 3, "max_verify_claims": 2,
        "votes_per_claim": 1, "refutations_required": 1, "max_workers": 2,
    },
    # ~26 agent calls — decent coverage, light adversarial check
    "medium": {
        "angles": 4, "max_fetch": 8, "max_verify_claims": 6,
        "votes_per_claim": 2, "refutations_required": 2, "max_workers": 4,
    },
    # ~46 agent calls — original hardcoded defaults, kept as the default tier
    "high": {
        "angles": 5, "max_fetch": 15, "max_verify_claims": 12,
        "votes_per_claim": 2, "refutations_required": 2, "max_workers": 6,
    },
    # ~147 agent calls — deep, wide research with 3-vote adversarial verification
    "ultra": {
        "angles": 10, "max_fetch": 30, "max_verify_claims": 35,
        "votes_per_claim": 3, "refutations_required": 2, "max_workers": 10,
    },
}

DEFAULT_TIER = "high"  # preserves pre-existing default behavior

# Hard ceiling: no tier or manual env override may push concurrent agent
# threads past this, no matter how large max_verify_claims/votes_per_claim get.
HARD_MAX_WORKERS = 20


def resolve_tier(tier_name: str) -> Dict[str, int]:
    key = (tier_name or DEFAULT_TIER).strip().lower()
    return TIER_PRESETS.get(key, TIER_PRESETS[DEFAULT_TIER])
