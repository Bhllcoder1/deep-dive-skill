"""Phase 1 — split the question into complementary search angles."""

from core import prompts, validate
from core.context import RunContext
from core.schemas import SCOPE_SCHEMA
from core.state import RunState

NAME = "Scope"


def _schema(max_angles: int) -> dict:
    """Keep the structured-output schema compatible with every configured tier."""
    schema = dict(SCOPE_SCHEMA)
    properties = dict(SCOPE_SCHEMA["properties"])
    angles = dict(properties["angles"])
    angles.update({"minItems": 1, "maxItems": max_angles})
    properties["angles"] = angles
    schema["properties"] = properties
    return schema


def run(ctx: RunContext, state: RunState) -> None:
    n = ctx.cfg.angles
    ctx.phase("1/5", f"Scope — soruyu {n} search angle'a böl: {state.question[:80]}...")
    scope = ctx.agent(prompts.scope(state.question, n), _schema(n), "scope", "Scope")
    if not scope:
        state.result = {"error": "Scope agent returned no valid JSON result.", "question": state.question}
        return
    state.angles = validate.valid_angles(scope.get("angles"), n)
    if not state.angles:
        state.result = {"error": "No valid search angles generated from scope.", "question": state.question}
        return
    ctx.log(f"Soru {len(state.angles)} angle'a bölündü: {', '.join(a['label'] for a in state.angles)}")
