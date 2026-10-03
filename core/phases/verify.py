"""Phase 4 — N independent adversarial verifiers per claim, then a threshold vote."""

from core import prompts, validate
from core.context import RunContext
from core.schemas import VERDICT_SCHEMA
from core.state import RunState

NAME = "Verify"


def run(ctx: RunContext, state: RunState) -> None:
    cfg = ctx.cfg
    ctx.phase("4/5", f"Verify — {len(state.ranked_claims)} claim, {cfg.votes_per_claim}-vote adversarial verification")
    votes = {id(claim): [] for claim in state.ranked_claims}

    def cast(claims, voters):
        functions = [(lambda claim=claim, voter=voter: ctx.agent(
            prompts.verify(claim, ctx.question, voter, cfg.votes_per_claim), VERDICT_SCHEMA,
            f"v{voter}:{claim['claim'][:40]}", "Verify")) for claim in claims for voter in voters]
        ctx.log(f"{len(functions)} verifier agent {'paralel' if len(functions) > 1 else 'sıralı'} çalışıyor "
                f"(max {cfg.max_workers} eşzamanlı)...")
        raw = ctx.run_parallel(functions)
        for position, claim in enumerate(claims):
            votes[id(claim)].extend(raw[position * len(voters):(position + 1) * len(voters)])

    def decided(claim):
        valid = [v for v in map(validate.valid_verdict, votes[id(claim)]) if v]
        refuted = sum(v["refuted"] for v in valid)
        return refuted >= cfg.refutations_required or len(valid) - refuted >= cfg.refutations_required

    # Early stopping: when V < 2R, R agreeing votes already fix the outcome (the rest cannot
    # change it), so only claims whose first R votes split or errored get the remaining voters.
    first = cfg.refutations_required if cfg.votes_per_claim < 2 * cfg.refutations_required else cfg.votes_per_claim
    cast(state.ranked_claims, range(first))
    undecided = [c for c in state.ranked_claims if not decided(c)] if first < cfg.votes_per_claim else []
    if undecided:
        cast(undecided, range(first, cfg.votes_per_claim))
    for claim in state.ranked_claims:
        raw = votes[id(claim)]
        valid = [verdict for verdict in (validate.valid_verdict(value) for value in raw) if verdict]
        refuted = sum(verdict["refuted"] for verdict in valid)
        support = len(valid) - refuted
        errored = len(raw) - len(valid)  # votes actually cast that came back unusable
        # A tie is unverified, not confirmed: support needs the same threshold as refutation.
        is_refuted = refuted >= cfg.refutations_required
        survives = support >= cfg.refutations_required and not is_refuted

        mark = "✓" if survives else ("✗" if is_refuted else "?")
        suffix = f" ({errored} errored)" if errored else ""
        ctx.log(f"  {mark} \"{claim['claim'][:50]}…\": {support}-{refuted}{suffix}")
        state.voted.append({**claim, "verdicts": valid, "refutedVotes": refuted,
                            "erroredVotes": errored, "survives": survives, "isRefuted": is_refuted})

    state.confirmed = [c for c in state.voted if c["survives"]]
    state.killed = [c for c in state.voted if c["isRefuted"]]
    state.unverified = [c for c in state.voted if not c["survives"] and not c["isRefuted"]]
    ctx.log(f"{len(state.confirmed)} confirmed, {len(state.killed)} refuted, {len(state.unverified)} unverified")
