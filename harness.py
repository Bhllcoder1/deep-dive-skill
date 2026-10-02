#!/usr/bin/env python3
"""CLI and Python API entrypoint for the Deep Dive research pipeline."""

import contextlib
import json
import os
import sys
import threading
from typing import Any, Dict, Mapping, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from core.config import OPTION_ENV, Config  # noqa: E402  (needs the path set above)
from core.logs import ensure_configured, get_logger  # noqa: E402

_CONFIG_MAP = OPTION_ENV  # public option -> environment variable (kept for compatibility)


def _runtime_names() -> set:
    from runtime import registered_names
    return set(registered_names()) | {"auto"}



def _error_result(question: str, message: str) -> Dict[str, Any]:
    return {"error": message, "question": question}


def _configure_dashboard(question: str, config: Config) -> Any:
    """Adapt the bundled Dashboard to the small interface expected by engine.run."""
    from core.dashboard import Dashboard

    dashboard = Dashboard()
    dashboard.title = "bdeep-research"
    dashboard.subtitle = question[:60]
    totals = {
        "Scope": 1,
        "Search": config.angles,
        "Fetch": config.max_fetch,
        "Verify": config.max_verify_claims,
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


def _start_dashboard(question: str, config: Config, runtime: Any) -> tuple[Any, Optional[threading.Event], Optional[threading.Thread]]:
    if not sys.stdout.isatty():
        return None, None, None
    try:
        dashboard = _configure_dashboard(question, config)
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
        get_logger("harness").warning(f"[dashboard] Could not start: {exc}")
        return None, None, None


def _stop_dashboard(stop_event: Optional[threading.Event], thread: Optional[threading.Thread]) -> None:
    if stop_event is not None:
        stop_event.set()
    if thread is not None:
        thread.join(timeout=1)


def deep_research(question: str, runtime_name: Optional[str] = None,
                  show_dashboard: bool = True, **kwargs) -> Dict[str, Any]:
    """Run the pipeline and return its structured research report.

    Keyword configuration mirrors the documented ``DR_*`` settings (see
    ``core.config.Config``). Each call gets its own immutable ``Config``: nothing global
    is mutated, so concurrent calls with different settings are safe.
    """
    if not isinstance(question, str):
        return _error_result("", "Research question must be a string.")
    question = question.strip()
    if not question:
        return _error_result(question, "No research question provided.")
    if runtime_name is not None and (not isinstance(runtime_name, str) or runtime_name not in _runtime_names()):
        return _error_result(question, f"Unsupported runtime: {runtime_name!r}.")

    try:
        config = Config.resolve(kwargs)
    except ValueError as exc:
        return _error_result(question, str(exc))

    ensure_configured()
    dashboard = stop_event = thread = None
    try:
        from core import engine
        from runtime import get_runtime

        runtime = get_runtime(None if runtime_name in (None, "auto") else runtime_name)

        get_logger("harness").info(f"\n{'=' * 50}\n🔬 Deep Dive Skill v2\n   Runtime: {runtime.name}\n"
                                   f"   Question: {question[:100]}\n{'=' * 50}")

        if show_dashboard:
            dashboard, stop_event, thread = _start_dashboard(question, config, runtime)
        result = engine.run(question, runtime=runtime, dashboard=dashboard, config=config)
        if not isinstance(result, dict):
            return _error_result(question, "Pipeline returned an invalid result.")
        result.setdefault("question", question)
        return result
    except KeyboardInterrupt:
        raise
    except TimeoutError as exc:
        return _error_result(question, f"Research timed out: {exc}")
    except Exception as exc:
        return _error_result(question, f"Research failed ({type(exc).__name__}): {exc}")
    finally:
        _stop_dashboard(stop_event, thread)


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

    confirmed = result.get("confirmed", [])
    if isinstance(confirmed, list) and confirmed:
        print(f"\n✓ Doğrulanmış (birleştirilmemiş) İddialar ({len(confirmed)})\n{'─' * 40}")
        for claim in confirmed:
            if not isinstance(claim, Mapping):
                print(f"  ✓ {_text(claim, '')[:100]}")
                continue
            print(f"  ✓ {_text(claim.get('claim'), '')[:100]}  [{_text(claim.get('vote'), '')}]")
            if claim.get("source"):
                print(f"      Kaynak: {_text(claim['source'])[:80]}")

    unverified = result.get("unverified", [])
    if isinstance(unverified, list) and unverified:
        print(f"\n? Doğrulanamayan İddialar ({len(unverified)})")
        for claim in unverified:
            text = claim.get("claim", "") if isinstance(claim, Mapping) else claim
            errored = claim.get("erroredVotes") if isinstance(claim, Mapping) else None
            suffix = f" ({errored} hatalı oy)" if errored else ""
            print(f"  ? {_text(text, '')[:100]}{suffix}")

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
    parser.add_argument("--runtime", choices=sorted(_runtime_names()), default="auto")
    parser.add_argument("--tier", choices=["low", "medium", "high", "ultra"],
                        help="Cost tier — bounds total agent calls (low~9, medium~26, high~46, ultra~147). Default: high")
    parser.add_argument("--angles", type=int, help="Search angle sayısı (tier'i override eder)")
    parser.add_argument("--refutations", type=int,
                        help="Çürütme için gereken oy sayısı, --votes'u aşamaz (tier'i override eder)")
    parser.add_argument("--max-fetch", type=int, help="Maksimum fetch URL (tier'i override eder)")
    parser.add_argument("--max-claims", type=int, help="Maksimum verify claim (tier'i override eder)")
    parser.add_argument("--votes", type=int, help="Claim başına verifier oy (tier'i override eder)")
    parser.add_argument("--max-workers", type=int, help="Eşzamanlı verifier agent sınırı, sabit tavan 20 (tier'i override eder)")
    parser.add_argument("--phase-budget", type=int,
                        help="Faz başına saniye bütçesi; dolunca yeni iş başlatılmaz (varsayılan 900)")
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
        "angles": args.angles,
        "refutations_required": args.refutations,
        "max_fetch": args.max_fetch,
        "max_verify_claims": args.max_claims,
        "votes_per_claim": args.votes,
        "max_workers": args.max_workers,
        "phase_budget_s": args.phase_budget,
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
