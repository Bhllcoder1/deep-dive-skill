#!/usr/bin/env python3
"""Generate docs/architecture-current.excalidraw and docs/architecture-target.excalidraw.

    python3 docs/tools/gen_architecture.py && python3 docs/tools/check_excalidraw.py docs/*.excalidraw
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from excalidraw_lib import Doc  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RED = "#e03131"
FLOW = "#1e1e1e"


def legend(d, x, y):
    d.note("legend_title", x, y, "LEJANT", 16)
    items = [("entry", "Giriş (CLI / API / panel.sh)"), ("core", "Çekirdek (core/)"),
             ("runtime", "Runtime soyutlaması + adaptörler"), ("external", "Dış servisler"),
             ("problem", "Sistem tasarımı sorunu / açık madde")]
    cx = x
    for i, (kind, text) in enumerate(items):
        d.box(f"legend_{kind}", cx, y + 30, 26, 18, None, kind)
        d.note(f"legend_{kind}_txt", cx + 32, y + 30, text, 13)
        cx += 32 + len(text) * 7.6 + 24
    d.box("legend_boundary", cx, y + 30, 40, 18, None, "boundary", dashed=True)
    d.note("legend_boundary_txt", cx + 46, y + 30, "Güven sınırı (kesikli)", 13)
    cx += 46 + 24 * 7.6 + 24
    d.note("legend_flow_txt", cx, y + 30, "→ ok = veri akışı", 13)


def boundary(d, id_, x, y, w, h, title):
    d.box(id_, x, y, w, h, None, "boundary", dashed=True, stroke_w=2, opacity=100)
    d.note(f"{id_}_title", x + 14, y + 8, title, 14, "#5f3dc4")


def mark(d, n, box_id, corner="tr", dx=0, dy=0):
    b = d.by_id[box_id]
    cx = b["x"] + (b["width"] - 6 if "r" in corner else 6) + dx
    cy = b["y"] + (2 if "t" in corner else b["height"] - 2) + dy
    d.marker(f"m{n}", cx, cy, n)


# ───────────────────────── CURRENT (baseline d20e154) ─────────────────────────

VIOLATIONS = [
    (1, "SRP — engine.py 552 satır: prompt + doğrulama + akış + rapor bir arada", "✓ düzeltildi 9693fc3"),
    (2, "Global durum — import-anı config + importlib.reload + RLock; eşzamanlı çağrılar seri", "✓ düzeltildi 9693fc3"),
    (3, "KRİTİK: Search fazı rt.web_search() çağırmıyor, LLM URL uyduruyor", "✓ düzeltildi be49fc9"),
    (4, "Search/Fetch sıralı (README/log 'paralel' diyor); faz bütçesi yok", "✓ düzeltildi 9693fc3"),
    (5, "Enjeksiyon — panel.sh soruyu python -c içine gömüyor", "✓ düzeltildi 9ce69b7"),
    (6, "OCP — yeni adaptör 3 dosya; _RUNTIME_REGISTRY hep None, hiç okunmuyor", "✓ düzeltildi b92c8ce"),
    (7, "DRY — 10 birebir CLI adaptörü; JSON ×4, URL ×4, thread havuzu ×4", "✓ düzeltildi adc74ad, b92c8ce"),
    (8, "Shell injection — *_CLI override shell=True ile çalışıyor (CODEX_CLI=1 → komut)", "✓ düzeltildi b92c8ce"),
    (9, "SSRF — DNS sonrası IP kontrolü yok; 2130706433 geçer; hermes/claude curl -L kontrolsüz", "✓ düzeltildi adc74ad"),
    (10, "Prompt injection — çekilen içerik/claim/quote prompt'a ayraçsız giriyor", "✓ düzeltildi 9693fc3 (kısmen)"),
    (11, "Gözlemlenebilirlik — print/logging karışık, stdout kirleniyor, run id yok", "✓ düzeltildi 551a583"),
    (12, "N1 — CLI bulununca HTTP istemcisi kurulmuyor: fallback/web_search/web_fetch hep boş", "✓ düzeltildi b92c8ce"),
    (13, "Güvenilirlik — retry/backoff yok; Bearer anahtarı curl argv'sinde", "✓ düzeltildi 51ec850"),
    (14, "YAGNI/ISP — RuntimeCapabilities alanları hiç okunmuyor", "○ açık (API riski)"),
    (15, "Claude Code köprüsü yalnız istek gönderiyor, yanıt almıyor", "○ açık"),
    (16, "Ölü kod — core/agent.py, core/web.py hiçbir yerden import edilmiyor", "✓ silindi b92c8ce"),
    (17, "Dashboard — panel.sh modunda çöküyor, yalnız Scope fazını gösteriyor", "✓ düzeltildi 45cde65, 9693fc3"),
]


def current():
    d = Doc("architecture-current")
    d.note("title", 40, 14, "Deep Dive Skill — MEVCUT mimari (inceleme tabanı d20e154)", 26)
    d.note("subtitle", 40, 50, "Kırmızı numaralar = sistem tasarımı kurallarına uymayan noktalar (sağdaki liste). "
           "'✓' bu dalda düzeltildi, '○' hâlâ açık.", 14, "#495057")

    boundary(d, "bdA", 30, 90, 1560, 1010, "GÜVEN SINIRI A — yerel Python süreci (kendi kodumuz)")

    # entry
    d.box("cli", 90, 135, 400, 78, "CLI\nharness.py main()  --tier --max-fetch …\n(--angles/--refutations yok)", "entry", size=14)
    d.box("api", 590, 135, 400, 78, "Python API\ndeep_research(question, **kwargs)", "entry", size=14)
    d.box("panel", 1090, 135, 440, 78, "panel.sh  →  python3 -c \"…'$1'…\"\ncore/dashboard.py (TUI)", "entry", size=14)

    d.box("harness", 280, 275, 1040, 86,
          "harness.py — config doğrulama + os.environ overlay\nimportlib.reload(core.engine) + process RLock  (global durum)", "entry", size=15)

    d.box("engine", 100, 410, 1400, 290, "core/engine.py — 552 satır: prompt + doğrulama + akış + sonuç/rapor",
          "core", size=15, valign="top")
    names = [("scope", "1 Scope\nsoruyu angle'lara böler"),
             ("search", "2 Search\nLLM URL üretir\n(web_search yok), sıralı"),
             ("fetch", "3 Fetch\nsıralı; içerik ayraçsız\nprompt'a gömülür"),
             ("verify", "4 Verify\nN oy, bounded batch\n(kaynak metni yok)"),
             ("synth", "5 Synthesize\nyalnız doğrulanmış\nkaynakları citeler")]
    for i, (pid, label) in enumerate(names):
        d.box(pid, 130 + i * 272, 480, 245, 120, label, "core", size=14, bg="#ffffff")
    for a, b in zip(["scope", "search", "fetch", "verify"], ["search", "fetch", "verify", "synth"]):
        d.arrow(f"f_{a}_{b}", a, b, "r", "l", color="#2f9e44")
    d.box("dead", 1180, 626, 300, 58, "core/agent.py + core/web.py\n(hiç import edilmiyor)", "problem", dashed=True, size=13)

    d.box("base", 200, 755, 1200, 92,
          "runtime/base.py — BaseRuntime ABC: agent_call · web_search · web_fetch · run_parallel · phase · log\n"
          "RuntimeCapabilities (okunmuyor) + runtime/__init__.py _RUNTIME_REGISTRY (hep None)", "runtime", size=14)

    d.box("native", 70, 915, 400, 150, "Native / özel\nhermes (curl)\nclaude_code (köprü: yalnız istek)", "runtime", size=14)
    d.box("cligrp", 990, 915, 560, 150,
          "CLI adaptörleri ×10 (birebir kopya)\ncodex cursor gemini copilot amazon_q\nwindsurf kimi glm minimax antigravity\nshell=True · setup() HTTP istemcisi kurmuyor", "runtime", size=14)
    d.box("gengrp", 510, 915, 440, 150, "Generic-only\ngeneric (taban) · aider · cline\nprint tabanlı log, kendi thread havuzu", "runtime", size=14)

    # external
    boundary(d, "bdB", 30, 1150, 1090, 190, "GÜVEN SINIRI B — ağ / güvenilmeyen dış dünya")
    boundary(d, "bdC", 1150, 1150, 440, 190, "GÜVEN SINIRI C — alt süreç (stdin/stdout)")
    d.box("llm", 70, 1210, 300, 100, "LLM API\nDeepSeek / OpenAI-uyumlu\n(Bearer anahtarı)", "external", size=14)
    d.box("search_ext", 410, 1210, 330, 100, "Arama\nDuckDuckGo · Google CSE · SearXNG", "external", size=14)
    d.box("targets", 780, 1210, 310, 100, "Hedef web siteleri\n(güvenilmeyen HTML/içerik)", "external", size=14)
    d.box("cliproc", 1190, 1210, 360, 100, "Yerel CLI ajanları\ncodex · gemini · cursor-agent …", "external", size=14)

    # flows
    d.arrow("a1", "cli", "harness", "b", "t", "kwargs", dst_frac=0.2, color=FLOW)
    d.arrow("a2", "api", "harness", "b", "t", "kwargs", color=FLOW)
    d.arrow("a3", "panel", "harness", "b", "t", "deep_research()", dst_frac=0.8, color=FLOW)
    d.arrow("a4", "harness", "engine", "b", "t", "DR_* env + reload", color=FLOW)
    d.arrow("a5", "engine", "base", "b", "t", "agent_call / web_fetch  (web_search: hiç)", color=FLOW)
    d.arrow("a6", "base", "native", "b", "t", color=FLOW, dst_frac=0.5, src_frac=0.2)
    d.arrow("a7", "base", "cligrp", "b", "t", color=FLOW, src_frac=0.85)
    d.arrow("a8", "base", "gengrp", "b", "t", color=FLOW, src_frac=0.5)
    d.arrow("a9", "native", "llm", "b", "t", "prompt/JSON", color=FLOW, src_frac=0.3, dst_frac=0.3)
    d.arrow("a10", "gengrp", "search_ext", "b", "t", "HTML/JSON", color=FLOW, src_frac=0.3, dst_frac=0.7)
    d.arrow("a11", "gengrp", "targets", "b", "t", "GET (SSRF yüzeyi)", color=FLOW, src_frac=0.75, dst_frac=0.4)
    d.arrow("a12", "cligrp", "cliproc", "b", "t", "prompt stdin / JSON stdout", color=FLOW, src_frac=0.5, dst_frac=0.5)
    d.arrow("a13", "gengrp", "llm", "b", "t", "OpenAI-uyumlu POST", color=FLOW, src_frac=0.08, dst_frac=0.85)

    # violation markers
    mark(d, 1, "engine")
    mark(d, 2, "harness")
    mark(d, 3, "search")
    mark(d, 4, "fetch", "tr")
    mark(d, 10, "fetch", "tl")
    mark(d, 5, "panel")
    mark(d, 17, "panel", "tl")
    mark(d, 6, "base")
    mark(d, 14, "base", "tl")
    mark(d, 7, "cligrp")
    mark(d, 8, "cligrp", "tl")
    mark(d, 12, "cligrp", "br")
    mark(d, 9, "targets")
    mark(d, 11, "gengrp")
    mark(d, 13, "llm")
    mark(d, 15, "native")
    mark(d, 16, "dead")

    # side list
    d.note("viol_title", 1640, 92, "İHLALLER", 18, RED)
    for i, (n, text, status) in enumerate(VIOLATIONS):
        y = 128 + i * 56
        d.marker(f"vm{n}", 1655, y + 17, n, r=13)
        d.box(f"vn{n}", 1680, y, 640, 46, f"{text}\n{status}", "problem", size=12, stroke=RED, bg="#fff5f5", stroke_w=1)

    legend(d, 40, 1370)
    return d


# ───────────────────────── TARGET (HEAD + proposals) ─────────────────────────

PROPOSALS = [
    ("p1", "Circuit breaker + token-bucket hız sınırlayıcı\n(LLM API ve arama, host başına)"),
    ("p2", "Yanıt önbelleği (url, prompt-hash) → idempotency / yeniden çalıştırma"),
    ("p3", "requests yolunda IP sabitleme (curl --resolve gibi)\n— kalan DNS-rebinding penceresi"),
    ("p4", "Doğrulayıcılara kaynak metin parçası ver (N6)"),
    ("p5", "İş birliği içinde iptal (threading.Event → RunContext)"),
    ("p6", "Ortak yardımcıları core'dan ayrı bir pakete taşı →\ncore↔runtime paket döngüsü kalkar"),
    ("p7", "RuntimeCapabilities'i engine kullansın ya da kaldırılsın;\nPipelineMonitor bağla/sil; Claude köprüsüne dönüş kanalı"),
]


def target():
    d = Doc("architecture-target")
    d.note("title", 40, 14, "Deep Dive Skill — HEDEF mimari (uygulananlar düz çizgi, önerilenler kesikli kırmızı)", 24)
    d.note("subtitle", 40, 50, "Yeşil/mavi/turuncu/gri = bu dalda uygulandı. Kırmızı kesikli = 'önerilen, uygulanmadı' "
           "(ayrıntı: docs/SYSTEM_DESIGN.md).", 14, "#495057")

    boundary(d, "bdA", 30, 90, 1560, 1130, "GÜVEN SINIRI A — yerel Python süreci (kendi kodumuz)")

    d.box("cli", 90, 135, 400, 70, "CLI  harness.py main()\n--angles --refutations --phase-budget …", "entry", size=14)
    d.box("api", 590, 135, 400, 70, "Python API\ndeep_research(question, **kwargs)", "entry", size=14)
    d.box("panel", 1090, 135, 440, 70, "panel.sh\nsoru argv ile (python3 -c \"$CODE\" \"$1\")", "entry", size=14)

    d.box("harness", 280, 255, 1040, 70,
          "harness.py — Config.resolve(kwargs) → değişmez Config\nglobal durum yok · reload yok · kilit yok (eşzamanlı çağrılar güvenli)", "entry", size=14)
    d.box("config", 1360, 255, 190, 70, "core/config.py\nConfig (frozen)", "core", size=14)

    d.box("engine", 100, 365, 1400, 300, "core/engine.py — ~57 satır orkestratör: PHASES = (scope, search, fetch, verify, synthesize)",
          "core", size=15, valign="top")
    names = [("scope", "core/phases/scope.py\nangle'lara böl"),
             ("search", "phases/search.py\nrt.web_search ‖ paralel\nLLM yalnız loglu yedek"),
             ("fetch", "phases/fetch.py\nsafe fetch ‖ paralel\nçitli prompt · quoteInSource"),
             ("verify", "phases/verify.py\nN oy · bounded batch\nbütçe: phase_budget_s"),
             ("synth", "phases/synthesize.py\nyalnız doğrulanmış kaynak\nyoksa salvage")]
    for i, (pid, label) in enumerate(names):
        d.box(pid, 130 + i * 272, 430, 245, 100, label, "core", size=13, bg="#ffffff")
    for a, b in zip(["scope", "search", "fetch", "verify"], ["search", "fetch", "verify", "synth"]):
        d.arrow(f"f_{a}_{b}", a, b, "r", "l", color="#2f9e44")
    d.box("ctx", 130, 565, 640, 80, "RunContext — korunmuş runtime çağrıları, gerçek agentCalls sayacı,\nfaz bütçesi/zamanlama, runId · RunState", "core", size=13, bg="#ffffff")
    d.box("pv", 800, 565, 680, 80, "prompts.py (untrusted çitleri) · validate.py · results.py\nschemas.py · tiers.py", "core", size=13, bg="#ffffff")

    d.box("libs", 100, 695, 1400, 84,
          "Ortak yardımcılar (tek kopya): urlsafe.py (sözcüksel + DNS) · safefetch.py (hop kontrolü + --resolve IP sabitleme, 0600 header dosyası) ·\n"
          "jsonparse.py · websearch.py (tek DDG ayrıştırıcı) · parallel.run_bounded · logs.py (stderr, redaksiyon, JSON, run_id)", "core", size=13)

    d.box("registry", 200, 815, 1200, 62,
          "runtime/__init__.py — gerçek registry: register(name, cls | 'modül:Sınıf', detect_env) → get_runtime() · detect() · registered_names()", "runtime", size=14)
    d.box("base", 200, 895, 1200, 56, "runtime/base.py — BaseRuntime ABC (agent_call · web_search · web_fetch · run_parallel · phase · log → logging)", "runtime", size=14)

    d.box("native", 70, 995, 400, 120, "hermes (curl, run_bounded)\nclaude_code (köprü: yalnız istek)\naider · cline (generic-only)", "runtime", size=14)
    d.box("cligrp", 990, 995, 560, 120,
          "runtime/cli.py — CliRuntime tabanı\n+ 10 veri-yalnız alt sınıf (komut adı, env değişkeni)\nshlex · shell YOK · HTTP istemcisi bağımsız", "runtime", size=14)
    d.box("gengrp", 510, 995, 440, 120, "generic (taban)\nretry + backoff + jitter\ncurl yalnız requests yoksa · SearXNG", "runtime", size=14)

    boundary(d, "bdB", 30, 1260, 1090, 190, "GÜVEN SINIRI B — ağ / güvenilmeyen dış dünya")
    boundary(d, "bdC", 1150, 1260, 440, 190, "GÜVEN SINIRI C — alt süreç (stdin/stdout)")
    d.box("llm", 70, 1320, 300, 100, "LLM API\nDeepSeek / OpenAI-uyumlu\n(anahtar: 0600 header dosyası)", "external", size=14)
    d.box("search_ext", 410, 1320, 330, 100, "Arama\nSearXNG → DDG HTML → Instant\n→ Google CSE", "external", size=13)
    d.box("targets", 780, 1320, 310, 100, "Hedef web siteleri\n(güvenilmeyen içerik: çitli)", "external", size=14)
    d.box("cliproc", 1190, 1320, 360, 100, "Yerel CLI ajanları\ncodex · gemini · cursor-agent …", "external", size=14)

    d.arrow("a1", "cli", "harness", "b", "t", "kwargs", dst_frac=0.2)
    d.arrow("a2", "api", "harness", "b", "t", "kwargs")
    d.arrow("a3", "panel", "harness", "b", "t", "deep_research()", dst_frac=0.8)
    d.arrow("a3b", "harness", "config", "r", "l", "Config")
    d.arrow("a4", "harness", "engine", "b", "t", "engine.run(config=…)")
    d.arrow("a5", "engine", "libs", "b", "t")
    d.arrow("a5b", "libs", "registry", "b", "t", "get_runtime()")
    d.arrow("a5c", "registry", "base", "b", "t")
    d.arrow("a6", "base", "native", "b", "t", src_frac=0.2)
    d.arrow("a7", "base", "cligrp", "b", "t", src_frac=0.85)
    d.arrow("a8", "base", "gengrp", "b", "t", src_frac=0.5)
    d.arrow("a9", "native", "llm", "b", "t", "prompt/JSON", src_frac=0.3, dst_frac=0.3)
    d.arrow("a10", "gengrp", "search_ext", "b", "t", "HTML/JSON", src_frac=0.3, dst_frac=0.7)
    d.arrow("a11", "gengrp", "targets", "b", "t", "GET (DNS+hop kontrollü)", src_frac=0.75, dst_frac=0.4)
    d.arrow("a12", "cligrp", "cliproc", "b", "t", "stdin / JSON stdout", src_frac=0.5, dst_frac=0.5)
    d.arrow("a13", "gengrp", "llm", "b", "t", "POST", src_frac=0.08, dst_frac=0.85)

    # proposals (dashed red)
    d.note("prop_title", 1640, 92, "ÖNERİLEN — UYGULANMADI", 18, RED)
    for i, (pid, text) in enumerate(PROPOSALS):
        y = 128 + i * 76
        d.box(pid, 1640, y, 680, 64, text, "problem", dashed=True, size=13, stroke=RED, bg="#fff5f5", stroke_w=2)
    # where the proposals attach
    d.box("p_breaker", 400, 1470, 340, 40, "⚠ p1/p2: breaker · limiter · önbellek", "problem", dashed=True, size=12, stroke=RED, bg="#fff5f5")
    d.arrow("pa1", "p_breaker", "search_ext", "t", "b", color=RED, dashed=True, src_frac=0.5, dst_frac=0.5)

    legend(d, 40, 1540)
    return d


def main():
    for name, builder in (("architecture-current.excalidraw", current), ("architecture-target.excalidraw", target)):
        doc = builder()
        path = os.path.abspath(os.path.join(OUT, name))
        doc.save(path)
        print("wrote", path, f"({len(doc.elements)} elements)")
        for warning in doc.warnings:
            print("  warning:", warning)


if __name__ == "__main__":
    main()
