#!/usr/bin/env python3
"""CLI and Python API entrypoint for the Deep Dive research pipeline."""

import contextlib
import importlib
import json
import os
import sys
import threading
from typing import Any, Dict, Mapping, Optional


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


_CONFIG_MAP = {
    "tier": "DR_COST_TIER",
    "angles": "DR_ANGLES",
    "max_fetch": "DR_MAX_FETCH",
    "max_verify_claims": "DR_MAX_VERIFY_CLAIMS",
    "votes_per_claim": "DR_VOTES_PER_CLAIM",
    "refutations_required": "DR_REFUTATIONS_REQUIRED",
    "max_workers": "DR_MAX_WORKERS",
}
_RUNTIMES = {
    "auto", "hermes", "claude_code", "generic", "aider", "codex", "cline",
    "cursor", "gemini", "copilot", "amazon_q", "windsurf", "kimi", "glm", "minimax", "antigravity",
}
_CONFIG_LOCK = threading.RLock()


def _error_result(question: str, message: str) -> Dict[str, Any]:
    return {"error": message, "question": question}


def _coerce_positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if number < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return number


def _resolve_config(overrides: Mapping[str, Any]) -> Dict[str, str]:
    unknown = set(overrides) - set(_CONFIG_MAP)
    if unknown:
        raise ValueError(f"Unsupported configuration option(s): {', '.join(sorted(unknown))}.")

    from core.tiers import HARD_MAX_WORKERS, resolve_tier

    raw_tier = overrides.get("tier", os.environ.get("DR_COST_TIER", ""))
    tier = str(raw_tier or "high").strip().lower()
    if tier not in {"low", "medium", "high", "ultra"}:
        raise ValueError("tier must be one of: low, medium, high, ultra.")

    tier_config = resolve_tier(tier)
    resolved = {"DR_COST_TIER": tier}
    for option, env_key in _CONFIG_MAP.items():
        if option == "tier":
            continue
        raw_value = overrides.get(option, os.environ.get(env_key, tier_config[option]))
        resolved[env_key] = str(_coerce_positive_int(option, raw_value))

    votes = int(resolved["DR_VOTES_PER_CLAIM"])
    refutations = int(resolved["DR_REFUTATIONS_REQUIRED"])
    if refutations > votes:
        raise ValueError("refutations_required cannot exceed votes_per_claim.")
    if int(resolved["DR_MAX_WORKERS"]) > HARD_MAX_WORKERS:
        raise ValueError(f"max_workers cannot exceed the hard limit of {HARD_MAX_WORKERS}.")
    return resolved


@contextlib.contextmanager
def _temporary_environ(values: Mapping[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _configure_dashboard(question: str, config: Mapping[str, str]) -> Any:
    """Adapt the bundled Dashboard to the small interface expected by engine.run."""
    from core.dashboard import Dashboard

    dashboard = Dashboard()
    dashboard.title = "bdeep-research"
    dashboard.subtitle = question[:60]
    totals = {
        "Scope": 1,
        "Search": int(config["DR_ANGLES"]),
        "Fetch": int(config["DR_MAX_FETCH"]),
        "Verify": int(config["DR_MAX_VERIFY_CLAIMS"]),
        "Synthesize": 1,
    }
    for phase in dashboard.phases:
        phase["total"] = totals.get(phase["name"], phase["total"])
        phase["completed"] = 0
        phase["status"] = "idle"
        phase["agents"] = []

    def select_phase(name: str) -> None:
        target = name.split("—", 1)[0].strip()
        for index, phase in enumerate(dashboard.phases):
            if phase["name"] == target:
                if phase["status"] == "idle":
                    phase["status"] = "running"
                dashboard.selected_idx = index
                return

    dashboard.select_phase = select_phase
    return dashboard


def _start_dashboard(question: str, config: Mapping[str, str], runtime: Any) -> tuple[Any, Optional[threading.Event], Optional[threading.Thread]]:
    if not sys.stdout.isatty():
        return None, None, None
    try:
        dashboard = _configure_dashboard(question, config)
        runtime._dashboard = dashboard
        stop_event = threading.Event()

        def render_loop() -> None:
            try:
                sys.stdout.write("\033[2J\033[H")
                while not stop_event.is_set():
                    sys.stdout.write("\033[H" + dashboard.render())
                    sys.stdout.flush()
                    stop_event.wait(0.5)
            except (BrokenPipeError, OSError):
                stop_event.set()

        thread = threading.Thread(target=render_loop, name="deep-research-dashboard", daemon=True)
        thread.start()
        return dashboard, stop_event, thread
    except Exception as exc:
        print(f"  [dashboard] Could not start: {exc}", file=sys.stderr)
        return None, None, None


def _stop_dashboard(stop_event: Optional[threading.Event], thread: Optional[threading.Thread]) -> None:
    if stop_event is not None:
        stop_event.set()
    if thread is not None:
        thread.join(timeout=1)


def deep_research(question: str, runtime_name: Optional[str] = None,
                  show_dashboard: bool = True, **kwargs) -> Dict[str, Any]:
    """Run the pipeline and return its structured research report.

    Keyword configuration mirrors the documented ``DR_*`` settings. Each call
    is isolated: overrides apply while its pipeline is running and are restored
    before this function returns.
    """
    if not isinstance(question, str):
        return _error_result("", "Research question must be a string.")
    question = question.strip()
    if not question:
        return _error_result(question, "No research question provided.")
    if runtime_name is not None and (not isinstance(runtime_name, str) or runtime_name not in _RUNTIMES):
        return _error_result(question, f"Unsupported runtime: {runtime_name!r}.")

    try:
        config = _resolve_config(kwargs)
    except ValueError as exc:
        return _error_result(question, str(exc))

    engine_module = None
    with _CONFIG_LOCK:
        try:
            with _temporary_environ(config):
                dashboard = stop_event = thread = None
                try:
                    from runtime import get_runtime

                    # ``core.engine`` reads DR_* settings at import time. Reload it
                    # under the lock so this invocation receives its own settings.
                    engine_module = importlib.import_module("core.engine")
                    engine_module = importlib.reload(engine_module)
                    selected_runtime = None if runtime_name in (None, "auto") else runtime_name
                    runtime = get_runtime(selected_runtime)

                    print(f"\n{'=' * 50}")
                    print("🔬 Deep Dive Skill v2")
                    print(f"   Runtime: {runtime.name}")
                    print(f"   Question: {question[:100]}")
                    print(f"{'=' * 50}")

                    if show_dashboard:
                        dashboard, stop_event, thread = _start_dashboard(question, config, runtime)
                    result = engine_module.run(question, runtime=runtime, dashboard=dashboard)
                    if not isinstance(result, dict):
                        result = _error_result(question, "Pipeline returned an invalid result.")
                    else:
                        result.setdefault("question", question)
                    return result
                finally:
                    _stop_dashboard(stop_event, thread)
        except KeyboardInterrupt:
            raise
        except TimeoutError as exc:
            return _error_result(question, f"Research timed out: {exc}")
        except Exception as exc:
            return _error_result(question, f"Research failed ({type(exc).__name__}): {exc}")
        finally:
            # Restore engine defaults too, not just os.environ, so this call's
            # configuration cannot affect a later direct engine.run() call.
            if engine_module is not None:
                try:
                    importlib.reload(engine_module)
                except Exception as exc:
                    print(f"[deep-research] Could not restore engine configuration: {exc}", file=sys.stderr)


def _text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def print_report(result: Dict[str, Any], format: str = "text") -> None:
    """Print a structured report without crashing on a partial pipeline result."""
    if not isinstance(result, Mapping):
        print("\n❌ HATA: Pipeline returned an invalid result.")
        return

    if format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    if "error" in result:
        print(f"\n❌ HATA: {_text(result['error'])}")
        return

    stats = result.get("stats", {})
    stats = stats if isinstance(stats, Mapping) else {}
    print(f"\n{'=' * 60}\n📊 DEEP RESEARCH RAPORU\n{'=' * 60}")
    print(f"\n❓ Soru: {_text(result.get('question'))}")
    print(f"⚙ Runtime: {_text(stats.get('runtime', result.get('runtime', 'N/A')))}")
    print(f"\n📋 Executive Summary\n{'─' * 40}\n{_text(result.get('summary'), 'Yok')}")

    findings = result.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    if findings:
        print(f"\n📌 Bulgular ({len(findings)})\n{'─' * 40}")
        for index, finding in enumerate(findings, 1):
            if not isinstance(finding, Mapping):
                continue
            print(f"\n  [{index}] {_text(finding.get('claim'))}")
            print(f"      Güven: {_text(finding.get('confidence'))}")
            sources = finding.get("sources", [])
            if isinstance(sources, (list, tuple)) and sources:
                print(f"      Kaynak: {_text(sources[0])[:80]}")
            if finding.get("evidence"):
                print(f"      Kanıt: {_text(finding['evidence'])[:200]}")

    refuted = result.get("refuted", [])
    if isinstance(refuted, list) and refuted:
        print(f"\n✗ Çürütülen İddialar ({len(refuted)})")
        for claim in refuted:
            text = claim.get("claim", "") if isinstance(claim, Mapping) else claim
            print(f"  ✗ {_text(text, '')[:100]}")

    caveats = result.get("caveats", "")
    if caveats:
        print(f"\n⚠ Uyarılar\n{'─' * 40}\n{_text(caveats)}")

    open_questions = result.get("openQuestions", [])
    if isinstance(open_questions, list) and open_questions:
        print("\n❓ Açık Sorular")
        for item in open_questions:
            print(f"  ? {_text(item)}")

    if stats:
        print(f"\n📈 İstatistikler\n{'─' * 40}")
        for key, value in stats.items():
            if key != "runtime":
                print(f"  {key}: {_text(value)}")
    print(f"\n{'=' * 60}")


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deep Dive Skill v2 — Evrensel Araştırma Ajanı",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="?", help="Araştırma sorusu")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--runtime", choices=sorted(_RUNTIMES), default="auto")
    parser.add_argument("--tier", choices=["low", "medium", "high", "ultra"],
                        help="Cost tier — bounds total agent calls (low~8, medium~26, high~46, ultra~147). Default: high")
    parser.add_argument("--max-fetch", type=int, help="Maksimum fetch URL (tier'i override eder)")
    parser.add_argument("--max-claims", type=int, help="Maksimum verify claim (tier'i override eder)")
    parser.add_argument("--votes", type=int, help="Claim başına verifier oy (tier'i override eder)")
    parser.add_argument("--max-workers", type=int, help="Eşzamanlı verifier agent sınırı, sabit tavan 20 (tier'i override eder)")
    parser.add_argument("--output", "-o", type=str, help="Çıktı dosyası")
    parser.add_argument("--no-dashboard", action="store_true", help="Dashboard'u devre dışı bırak")
    args = parser.parse_args()

    if args.question == "panel":
        from core.dashboard import C
        print(f"{C.BOLD}{C.GREEN}━━━ Deep Dive Skill Control Panel{C.END}")
        print(f"  {C.DIM}Run in your terminal:{C.END}")
        print(f"  {C.BOLD}cd {_THIS_DIR} && python3 -m core.dashboard{C.END}")
        return 0

    question = args.question
    if not question:
        try:
            question = input("🔬 Araştırma sorusu: ").strip()
        except EOFError:
            parser.error("a research question is required when standard input is closed")
        if not question:
            parser.error("a non-empty research question is required")

    kwargs = {key: value for key, value in {
        "tier": args.tier,
        "max_fetch": args.max_fetch,
        "max_verify_claims": args.max_claims,
        "votes_per_claim": args.votes,
        "max_workers": args.max_workers,
    }.items() if value is not None}

    # JSON mode promises machine-readable stdout; all pipeline progress goes to stderr.
    output_stream = sys.stderr if args.format == "json" else contextlib.nullcontext()
    with contextlib.redirect_stdout(output_stream) if args.format == "json" else output_stream:
        result = deep_research(
            question,
            runtime_name=args.runtime,
            show_dashboard=not args.no_dashboard and args.format != "json",
            **kwargs,
        )
    print_report(result, format=args.format)

    safe_name = "".join(char if char.isalnum() or char in " _-" else "_" for char in question[:50]).strip()
    output_file = args.output or f"deep-research-{safe_name or 'report'}.json"
    try:
        with open(output_file, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False, default=str)
    except (OSError, TypeError, ValueError) as exc:
        print(f"\n❌ Rapor kaydedilemedi ({output_file}): {exc}", file=sys.stderr)
        return 1
    print(f"\n📁 Rapor kaydedildi: {output_file}", file=sys.stderr if args.format == "json" else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
