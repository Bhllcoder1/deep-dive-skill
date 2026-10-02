"""Phase 4 — N independent adversarial verifiers per claim, then a threshold vote."""

from core import prompts, validate
from core.context import RunContext
from core.schemas import VERDICT_SCHEMA
from core.state import RunState

NAME = "Verify"


def run(ctx: RunContext, state: RunState) -> None:
    cfg = ctx.cfg
    ctx.phase("4/5", f"Verify — {len(state.ranked_claims)} claim, {cfg.votes_per_claim}-vote adversarial verification")
    functions = [
        (lambda claim=claim, voter=voter: ctx.agent(
            prompts.verify(claim, ctx.question, voter, cfg.votes_per_claim), VERDICT_SCHEMA,
            f"v{voter}:{claim['claim'][:40]}", "Verify"))
        for claim in state.ranked_claims for voter in range(cfg.votes_per_claim)
    ]
    ctx.log(f"{len(functions)} verifier agent {'paralel' if len(functions) > 1 else 'sıralı'} çalışıyor "
            f"(max {cfg.max_workers} eşzamanlı)...")
    verdicts = ctx.run_parallel(functions)

    for index, claim in enumerate(state.ranked_claims):
        raw = verdicts[index * cfg.votes_per_claim:(index + 1) * cfg.votes_per_claim]
        valid = [verdict for verdict in (validate.valid_verdict(value) for value in raw) if verdict]
        refuted = sum(verdict["refuted"] for verdict in valid)
        support = len(valid) - refuted
        errored = cfg.votes_per_claim - len(valid)
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
