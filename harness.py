#!/usr/bin/env python3
"""
Deep Dive Skill v2 — Universal Multi-Platform Research Agent.

Pipeline: Scope → Search → Fetch → Verify → Synthesize

Her platform KENDİ doğal API'sini kullanır:
  • Hermes Agent    → terminal + curl + threading
  • Claude Code     → built-in agent(), parallel(), WebSearch, WebFetch
  • Aider           → generic fallback (DDG + requests + threading)
  • Codex CLI       → generic fallback
  • Cline/Roo       → generic fallback
  • Generic Python  → requests/curl + DDG + threading

Dashboard (CANLI):
  • pipeline çalışırken otomatik açılır
  • ↑↓ fazlar arası geçiş · enter genişlet · f filtre · s kaydet · esc geri · q çıkış

Kullanım:
    python3 harness.py "Araştırma konusu"          # pipeline + dashboard
    python3 harness.py --no-dashboard "soru"       # sadece pipeline
    DR_RUNTIME=hermes python3 harness.py "konu"
"""

import json
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

from core.dashboard import C

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)


def deep_research(question: str, runtime_name: Optional[str] = None,
                  show_dashboard: bool = True, **kwargs) -> Dict[str, Any]:
    """
    Deep research çalıştırır. Pipeline + otomatik dashboard.

    Args:
        question: Araştırma sorusu
        runtime_name: Zorla runtime seçimi
        show_dashboard: Dashboard gösterilsin mi? (default: True)
        **kwargs: DR_* environment variable override'ları
    """
    config_map = {
        "tier": "DR_COST_TIER",
        "angles": "DR_ANGLES",
        "max_fetch": "DR_MAX_FETCH",
        "max_verify_claims": "DR_MAX_VERIFY_CLAIMS",
        "votes_per_claim": "DR_VOTES_PER_CLAIM",
        "refutations_required": "DR_REFUTATIONS_REQUIRED",
        "max_workers": "DR_MAX_WORKERS",
    }
    for k, v in kwargs.items():
        env_key = config_map.get(k)
        if env_key:
            os.environ[env_key] = str(v)

    if runtime_name:
        os.environ["DR_RUNTIME"] = runtime_name

    from runtime import get_runtime
    rt = get_runtime(runtime_name)

    # Resolve the active tier (explicit DR_* env vars above already override it)
    from core.tiers import resolve_tier
    _tier_cfg = resolve_tier(os.environ.get("DR_COST_TIER", ""))
    dash_angles = int(os.environ.get("DR_ANGLES", _tier_cfg["angles"]))
    dash_fetch = int(os.environ.get("DR_MAX_FETCH", _tier_cfg["max_fetch"]))
    dash_claims = int(os.environ.get("DR_MAX_VERIFY_CLAIMS", _tier_cfg["max_verify_claims"]))

    print(f"\n{'='*50}")
    print(f"🔬 Deep Dive Skill v2")
    print(f"   Runtime: {rt.name}")
    print(f"   Question: {question[:100]}...")
    print(f"{'='*50}")

    # Dashboard'u başlat (ayrı thread'de)
    dashboard = None
    dash_thread = None
    
    if show_dashboard:
        try:
            from core.dashboard import Dashboard
            dashboard = Dashboard(
                title="bdeep-research",
                subtitle=question[:60]
            )
            
            # Pipeline fazlarını dashboard'a ekle (aktif tier'e göre)
            dashboard.add_phase("Scope", total=1)
            dashboard.add_phase("Search", total=dash_angles)
            dashboard.add_phase("Fetch", total=dash_fetch)
            dashboard.add_phase("Verify", total=dash_claims)
            dashboard.add_phase("Synthesize", total=1)
            
            # Dashboard'u runtime'a bağla
            rt._dashboard = dashboard
            
            # Dashboard thread'i (canlı güncelleme)
            dash_stop = threading.Event()
            
            def dash_loop():
                """Dashboard canlı güncelleme döngüsü."""
                try:
                    os.system('clear')
                    while not dash_stop.is_set():
                        # Dashboard render
                        output = dashboard.render()
                        sys.stdout.write('\033[H' + output)
                        sys.stdout.flush()
                        dash_stop.wait(0.5)
                except:
                    pass
            
            dash_thread = threading.Thread(target=dash_loop, daemon=True)
            dash_thread.start()
            
        except Exception as e:
            print(f"  [dashboard] ⚠ Could not start: {e}")
            dashboard = None

    # Pipeline'ı çalıştır
    from core.engine import run
    result = run(question, runtime=rt, dashboard=dashboard)
    
    # Dashboard'u durdur
    if dashboard:
        dash_stop.set()
        time.sleep(0.3)
        # Son bir render
        try:
            dashboard.clear()
            dashboard.display()
        except:
            pass

    return result


def print_report(result: Dict[str, Any], format: str = "text") -> None:
    """Raporu yazdırır."""
    if "error" in result:
        print(f"\n❌ HATA: {result['error']}")
        return

    if format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    stats = result.get("stats", {})
    print(f"\n{'='*60}")
    print(f"📊 DEEP RESEARCH RAPORU")
    print(f"{'='*60}")
    print(f"\n❓ Soru: {result.get('question', 'N/A')}")
    print(f"⚙ Runtime: {stats.get('runtime', 'N/A')}")

    print(f"\n📋 Executive Summary")
    print(f"{'─'*40}")
    print(result.get("summary", "Yok"))

    findings = result.get("findings", [])
    if findings:
        print(f"\n📌 Bulgular ({len(findings)})")
        print(f"{'─'*40}")
        for i, f in enumerate(findings):
            print(f"\n  [{i+1}] {f.get('claim', 'N/A')}")
            print(f"      Güven: {f.get('confidence', 'N/A')}")
            sources = f.get('sources', [])
            if sources:
                print(f"      Kaynak: {sources[0][:80]}")
            if f.get('evidence'):
                print(f"      Kanıt: {f['evidence'][:200]}")

    refuted = result.get("refuted", [])
    if refuted:
        print(f"\n✗ Çürütülen İddialar ({len(refuted)})")
        for r in refuted:
            print(f"  ✗ {r.get('claim', '')[:100]}")

    caveats = result.get("caveats", "")
    if caveats:
        print(f"\n⚠ Uyarılar\n{'─'*40}\n{caveats}")

    open_qs = result.get("openQuestions", [])
    if open_qs:
        print(f"\n❓ Açık Sorular")
        for q in open_qs:
            print(f"  ? {q}")

    if stats:
        print(f"\n📈 İstatistikler\n{'─'*40}")
        for k, v in stats.items():
            if k != "runtime":
                print(f"  {k}: {v}")

    print(f"\n{'='*60}")


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Deep Dive Skill v2 — Evrensel Araştırma Ajanı",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="?", help="Araştırma sorusu")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--runtime", choices=["auto", "hermes", "claude_code", "generic", "aider", "codex", "cline"],
                        default="auto")
    parser.add_argument("--tier", choices=["low", "medium", "high", "ultra"],
                        help="Cost tier — bounds total agent calls (low~8, medium~26, high~46, ultra~147). Default: high")
    parser.add_argument("--max-fetch", type=int, help="Maksimum fetch URL (tier'i override eder)")
    parser.add_argument("--max-claims", type=int, help="Maksimum verify claim (tier'i override eder)")
    parser.add_argument("--votes", type=int, help="Claim başına verifier oy (tier'i override eder)")
    parser.add_argument("--max-workers", type=int, help="Eşzamanlı verifier agent sınırı, sabit tavan 20 (tier'i override eder)")
    parser.add_argument("--output", "-o", type=str, help="Çıktı dosyası")
    parser.add_argument("--no-dashboard", action="store_true", help="Dashboard'u devre dışı bırak")

    args = parser.parse_args()
    
    # panel komutu: direkt dashboard aç
    if args.question == "panel":
        os.system('clear')
        print(f"{C.BOLD}{C.GREEN}━━━ Deep Dive Skill Control Panel{C.END}")
        print(f"  {C.DIM}Run in your terminal:{C.END}")
        print(f"  {C.BOLD}cd ~/Desktop/deep-dive-skill && python3 -m core.dashboard{C.END}")
        print(f"\n  {C.DIM}Or use PTY mode:{C.END}")
        print(f"  {C.BOLD}python3 -c \"from core.dashboard import main; main()\"{C.END}")
        return

    question = args.question
    if not question:
        question = input("🔬 Araştırma sorusu: ").strip()
        if not question:
            parser.print_help()
            sys.exit(1)

    kwargs = {}
    if args.tier: kwargs["tier"] = args.tier
    if args.max_fetch: kwargs["max_fetch"] = args.max_fetch
    if args.max_claims: kwargs["max_verify_claims"] = args.max_claims
    if args.votes: kwargs["votes_per_claim"] = args.votes
    if args.max_workers: kwargs["max_workers"] = args.max_workers

    result = deep_research(
        question,
        runtime_name=args.runtime if args.runtime != "auto" else None,
        show_dashboard=not args.no_dashboard,
        **kwargs
    )
    print_report(result, format=args.format)

    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in question[:50]).strip()
    output_file = args.output or f"deep-research-{safe_name}.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Rapor kaydedildi: {output_file}")


if __name__ == "__main__":
    main()
