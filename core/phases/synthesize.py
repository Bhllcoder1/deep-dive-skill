"""Phase 5 — merge confirmed claims into a cited report; salvage if synthesis is unusable."""

from core import prompts, results, validate
from core.context import RunContext
from core.schemas import REPORT_SCHEMA
from core.state import RunState

NAME = "Synthesize"


def run(ctx: RunContext, state: RunState) -> None:
    ctx.phase("5/5", "Synthesize — rapor sentezleniyor")
    if not state.confirmed:
        ctx.end_phase()
        state.result = results.nothing_confirmed(ctx, state)
        return
    reply = ctx.agent(prompts.synthesis(state.question, state.confirmed, state.killed, state.unverified,
                                        ctx.cfg.votes_per_claim), REPORT_SCHEMA, "synthesize", "Synthesize")
    # Only sources that survived verification may be cited.
    report = validate.valid_report(reply, {claim["sourceUrl"] for claim in state.confirmed})
    ctx.end_phase()
    state.result = results.success(ctx, state, report) if report else results.salvage(ctx, state)
