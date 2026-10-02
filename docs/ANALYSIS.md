# Deep Dive Skill — Mimari Analiz ve Doğrulama Raporu

**Kapsam:** `README.md`, `harness.py`, `panel.sh`, `core/*.py`, `runtime/*.py`, `runtime/adapters/*.js`, `CODEX_CHANGES.md`, `CODEX_CHANGES/*.md`. `Notes/` ve `__pycache__` kapsam dışı.

**Satır referansları:** Aksi belirtilmedikçe tüm `dosya:satır` referansları **başlangıç commit'indeki (`d20e154`)** dosyalara aittir; `git show d20e154:<dosya>` ile görülebilir. Her referans okunarak doğrulanmıştır; kesin doğrulanamayanlar **doğrulanamadı** olarak işaretlidir. "Durum" sütunundaki commit'ler bu daldaki (`feat/architecture-review`) düzeltmelerdir.

**Yöntem:** Statik okuma + grep + ağsız çalıştırma (N1, N2, F10 kod değiştirilmeden çalıştırılarak kanıtlandı). Analiz Opus ile yürütüldü; düzeltmeler ve doğrulama testleri ayrı yapıldı (`tests/`, 122 test).

## 1. Modül sorumlulukları ve bağımlılıklar (başlangıç durumu)

**Gerçek import grafiği**
- `harness.py` → `core.tiers` (55), `runtime.get_runtime` (186), `core.engine` import+reload (190-191, 222), `core.dashboard` (95, 317)
- `core/engine.py` → `core.schemas`, `core.tiers`, `runtime` (11-13)
- `core/__init__.py` → `engine.run`, `monitor` (7-9)
- `core/dashboard.py` → `harness.deep_research` (döngüsel, lazy; 98), `core.monitor.ModelConfig` (333)
- `runtime/__init__.py` → `base` + lazy adaptörler (26, 113-157)
- 12 adaptör (aider, cline, 10 CLI) → `runtime.generic`; `runtime/_cli_parallel.py` → `core.parallel` (5)
- `panel.sh` → `core.dashboard`, `harness`; `claude-code-wrapper.js` → `harness.py` (spawn); `claude-code-workflow.js` bağımsız
- **Hiçbir yerden import edilmeyen:** `core/agent.py`, `core/web.py` (grep sonucu 0). `core/monitor.py`'den yalnızca `ModelConfig` kullanılıyor (dashboard.py:333-335); `PipelineMonitor` yalnızca docstring'de (monitor.py:332) ve export'ta (core/__init__.py:8).

| Modül | Sorumluluk | Not |
|---|---|---|
| `harness.py` | CLI (`main` 295-360), API (`deep_research` 159-224), config doğrulama (50-76), env overlay + reload (79-90, 181-224), `print_report` (233-292), TTY dashboard (93-156) | 5 sorumluluk |
| `core/engine.py` | Orkestrasyon (43-200), import-anı config (16-40), runtime sınırları (203-276), doğrulama (279-423), prompt'lar (426-490), sonuç kurucuları (493-552) | 552 satır, 6 sorumluluk |
| `core/schemas.py` | 5 JSON şeması | SCOPE `minItems=3` (14) engine'de ezilir (engine.py:254-262) |
| `core/tiers.py` | Presetler, `HARD_MAX_WORKERS=20` (43) | |
| `core/parallel.py` | `pipeline`/`parallel`/`_threaded_parallel` | Yalnız `_threaded_parallel` + `_validate_max_workers` kullanılıyordu |
| `core/agent.py` | Eski LLM çağrısı + şema doğrulayıcı | **Ölü** |
| `core/web.py` | DDG HTML/Google/SearXNG arama + fetch | **Ölü** (SearXNG yalnız burada vardı) |
| `core/monitor.py` | İzleme, maliyet, `ModelConfig` | `PipelineMonitor` kullanılmıyor |
| `core/dashboard.py` | TUI, `PipelineController`, `HistoryManager` | Çalışma zamanı hataları (N2) |
| `runtime/__init__.py` | `detect` (29-87), `get_runtime` (99-157) | Registry ölü |
| `runtime/base.py` | `BaseRuntime` ABC, `RuntimeCapabilities` | Capability modeli kullanılmıyor |
| `runtime/generic.py` | OpenAI-uyumlu LLM, DDG + Google, fetch, el yapımı havuz | 12 adaptörün tabanı |
| `runtime/hermes.py` | curl ile LLM/arama/fetch, queue havuzu | generic ile örtüşür |
| `runtime/claude_code.py` | stderr marker + requests fallback | Köprü tek yönlü |
| 10 CLI adaptörü | stdin ile CLI, JSON parse, generic fallback | Kopya (F5d), fallback bozuk (N1) |
| `adapters/claude-code-wrapper.js` | harness spawn, marker kuyruğu | Kuyruklar tüketilmiyor |
| `adapters/claude-code-workflow.js` | Pipeline'ın ayrı JS kopyası | Davranış farkı (N7) |
| `panel.sh` | Dashboard başlatıcı | Enjeksiyon (F3) |

## 2. README iddiaları ve gerçek kod

| ID | İddia | Gerçek (başlangıç) | Kanıt | Durum |
|---|---|---|---|---|
| R1 | Her angle aranır (README:228) | Engine `web_search`'ü hiç çağırmıyordu, URL'leri LLM üretiyordu | engine.py:81-101, 438-444 | `be49fc9` |
| R2 | Generic yol "optional SearXNG" (25, 141) | Generic SearXNG desteklemiyordu; yalnız ölü `core/web.py:424-453` | grep `searx` runtime/ → 0 | `b92c8ce` (generic'e taşındı) |
| R3 | CLI başarısızsa generic'e düşer (54) | CLI bulununca fallback + arama/fetch ölüydü | N1 | `b92c8ce` |
| R4 | `DR_RUNTIME` listesi (132) | `antigravity` yok | runtime/__init__.py:152-154 | README düzeltildi |
| R5 | CLI override tablosu (151-161) | `ANTIGRAVITY_CLI` yok | antigravity.py:17 | README düzeltildi |
| R6 | Clone URL (31) | `YOUR_USERNAME`; User-Agent'ta da | generic.py:25 | düzeltildi → `Bhllcoder1` |
| R7 | Mimari ağacı (186-223) | `antigravity.py`, `_cli_parallel.py` yok | README:207-217 | ağaç yeniden yazıldı |
| R8 | Unverified çıktısı (47) | Metin raporu yalnız refuted basıyordu | harness.py:270-275 | `a0cd59e` |
| R9 | low ≈ 9 çağrı (114-118) | `tiers.py:17` ve `harness.py:307` "~8" diyordu (formül: 2+2+3+2 = 9) | tutarsızlık | düzeltildi (~9) |
| R10 | Canlı dashboard (50) | `panel.sh "soru"` çöküyordu; dashboard yalnız Scope gösteriyordu | N2, N3 | `45cde65`, `9693fc3` |
| R11 | `LLM_PROVIDER` "recognized" (142-144) | `ModelConfig.switch` hiç çağrılmıyor (monitor.py:237-255); `m` yalnız listeler (dashboard.py:331-335) | grep `.switch(` → 0 | **açık** (öneri) |
| R12 | "Ties remain unverified" (23) | Python doğru (engine.py:163-164); JS'de 1-1 *survives* | claude-code-workflow.js:205 | `51ec850` |
| R13 | `OPENCLAW_MODE` → generic (163) | Doğru ama sessiz ölü dal | runtime/__init__.py:62-63 | dal silindi |
| R14 | wrapper "bridge" (220) | wrapper.js:11 "Feeds results back" der; geri besleme yok | wrapper.js:46-56 | **açık** (öneri, README zaten "request-only" der) |
| R15 | CODEX_CHANGES/web.md:3 Instant Answer değişti | Yalnız ölü `core/web.py`'de; generic hâlâ önce Instant Answer kullanıyordu | generic.py:260-264 | `c8f1684` (HTML öncelikli) |
| R16 | readme_and_cleanup.md:6 "14 adapters" | 15 | runtime/__init__.py:160-175 | CODEX_CHANGES başına tarihçe notu |
| R17 | engine.md:7-8 injection/özel IP engellendi | Yalnız prompt uyarısı (engine.py:452) ve literal IP kontrolü | F10, F11 | `adc74ad`, `9693fc3` |

## 3. Önceki incelemenin maddeleri — doğrulama sonuçları

| # | Madde | Sonuç | Kanıt (başlangıç) | Düzeltme |
|---|---|---|---|---|
| F1 | **KRİTİK** Search fazı `rt.web_search()` çağırmıyor | **DOĞRULANDI** | engine.py:81-101 her angle için `_agent_call(_search_prompt…)`; engine.py:438-444 LLM'den URL ister; `web_search(` çağrısı yalnız docstring'de (runtime/__init__.py:19) | `be49fc9`: önce `web_search`, boşsa **loglanan** LLM yedeği (`stats.searchFallbacks`, `sources[].via`); `9693fc3`: paralel |
| F2 | `agentCalls` tahmin | **DOĞRULANDI** | engine.py:519 `1+angles+len(fetched)+verifier+1`; fetch'i başarısız (çağrı yapılmayan) kaynakları da sayar (111-127); no_confirmed/salvage'da sentez olmadan +1 (537, 551); `_empty_result` farklı anahtar kümesi (526-527) | `be49fc9`: iş parçacığı-güvenli gerçek sayaç |
| F3 | **Güvenlik** `panel.sh` enjeksiyonu | **DOĞRULANDI** | panel.sh:33-48 çift tırnaklı Python kaynağında `'$1'` (39, 42); `'` sözdizimini bozar, `'); import os; …` kod çalıştırır. `python3 -` kullanılamaz: dashboard stdin'den okur (dashboard.py:451-469) | `9ce69b7`: `python3 -c "$CODE" "$1"`, soru `sys.argv[1]` |
| F4 | CLI `--angles/--refutations`; `print_report` | **DOĞRULANDI** | harness.py:299-314 bayrak yok (API'de var 18-26); `print_report` unverified ve salvage `confirmed` (engine.py:546-548) basmıyor | `a0cd59e` (+ `--phase-budget` `9693fc3`) |
| F5a | JSON çıkarma ×4 | **DOĞRULANDI** | core/agent.py:44-73, generic.py:225-249 (**`schema` kullanılmıyor**), hermes.py:243-277 (yalnız üst düzey `required`), claude_code.py:155-188 (`required` + `None` değil), engine.py:239-251 | `adc74ad`: `core/jsonparse.py` |
| F5b | URL güvenliği ×3+ | **DOĞRULANDI** | engine.py:323-347, generic.py:434-448, core/web.py:46-59 (özel IP yok), hermes.py:286-290 (özel IP yok), claude_code.py:232-235 (yalnız şema) | `adc74ad`: `core/urlsafe.py` |
| F5c | Paralel ×2+ | **DOĞRULANDI** | core/parallel.py:94-110, generic.py:459-511, hermes.py:377-440, claude_code.py:257-282; hata sözleşmeleri farklı (claude_code `[]` döner 260-262, diğerleri raise) | `adc74ad`: `core.parallel.run_bounded` |
| F5d | 10 CLI adaptörü birebir | **DOĞRULANDI** | codex.py:52 vs cursor.py:52 vb.: yalnız docstring/log ve `shutil.which` satırı farklı; copilot (53-58), kimi, glm tek satır fark | `b92c8ce`: `runtime/cli.py` `CliRuntime` |
| F5+ | LLM payload ×5, `~/.env` okuma ×3 | **DOĞRULANDI** | agent.py:177-187, generic.py:128-139, hermes.py:143-153, claude_code.py:117-127; agent.py:165, generic.py:82-93, hermes.py:67-76 | **açık** (öneri: tek istemci sınıfı) |
| F6a | `core/agent.py`, `core/web.py` engine'de kullanılmıyor | **DOĞRULANDI** | grep 0; web.py:1 "used by the generic runtime" yanlış; web.py:283-292 `_hermes_search` hep `[]` | `b92c8ce`: silindi (SearXNG taşındı) |
| F6b | `_RUNTIME_REGISTRY` hep `None` | **DOĞRULANDI** | runtime/__init__.py:91-96, 160-175; `get_runtime` (99-157) okumaz | `b92c8ce`: gerçek registry |
| F6c | `OPENCLAW_MODE` adaptörsüz | **DOĞRULANDI** | runtime/__init__.py:62-63, 155-157 | `b92c8ce`: ölü dal silindi |
| F6d | Claude köprüsü yalnız istek | **DOĞRULANDI** | claude_code.py:93-103 marker + koşulsuz generic; wrapper.js:53-56 kuyruklar (70, 77, 84) okunmuyor; stdin (48) yazılmıyor; wrapper.js:18 olmayan `.sh`'ye atıf | **açık** (öneri); README zaten dürüst |
| F6e | Search/Fetch sıralı, "paralel" | **KISMEN** — README açıkça iddia etmiyor (74); engine.py:76 "paralel web araması", tiers.py:5 ve JS meta söylüyor | engine.py:81, 109 sıralı; yalnız Verify paralel (152) | `9693fc3`: gerçekten paralel |
| F7 | README `antigravity`/`YOUR_USERNAME` | **DOĞRULANDI** | README:132, 151-161, 31; generic.py:25 | düzeltildi (`Bhllcoder1`; repo içinden doğrulanamadı, kullanıcı belirtti) |
| F8 | Kullanılmayan `RuntimeCapabilities` alanları | **DOĞRULANDI** | base.py:54-78 alanlar, 80-122 doğrulama; `capabilities` (169-171) hiç override edilmez, `.capabilities`/`describe()` hiç okunmaz | **açık** (API: `BaseRuntime.capabilities` korunuyor) |
| F9 | `shell=True` | **DOĞRULANDI** (+ ağırlaştırıcı) | codex.py:44-49 çok kelimeli **veya PATH'te bulunamayan** değer → `_use_shell=True`; codex.py:85-86 `shell=True`; aynısı cursor.py:86, gemini.py:86, minimax.py:86, windsurf.py:86, kimi.py:92, copilot.py:89-90, glm.py:85, amazon_q.py:64, antigravity.py:61-64. `CODEX_CLI=1` (tespit bayrağı) shell'de `1` komutu olarak çalışırdı | `b92c8ce`: `shlex.split` + `shell=False`; çözülemeyen değer yok sayılır |
| F10 | SSRF: DNS sonrası kontrol yok | **DOĞRULANDI** | yalnız literal host kontrolü (engine.py:330-339, generic.py:441-448). **Kanıt:** `http://2130706433/` ve `http://127.1/` filtreden geçer, `gethostbyname` → 127.0.0.1. Yönlendirme: generic.py:386-397 yalnız literal; claude_code.py:242 `curl -sL` kontrolsüz; hermes.py:353 yalnız protokol | `adc74ad`: sayısal host reddi, `.local/.internal`, IPv4-mapped IPv6, DNS çözümleme, hop başına kontrol, `curl --resolve` ile IP sabitleme |
| F11 | Prompt injection | **KISMEN** | engine.py:452 uyarı var; içerik ayraçsız (454); claim/quote verifier (462-463) ve sentez (470-480) prompt'larına uyarısız girer; quote'un içerikte geçtiği denetlenmez (361-367) | `9693fc3`: `<untrusted_*>` çitleri, `quoteInSource` bayrağı |
| F12 | Import-anı config + `importlib.reload` | **DOĞRULANDI** | engine.py:17, 34-40; harness.py:190-191, 222; kilit (31, 181) yalnız harness çağrılarını korur; dashboard.py:97 `os.environ`'u kilitsiz kalıcı değiştirir | `9693fc3`: `Config`, reload/kilit yok; `45cde65`: dashboard env değiştirmiyor |
| F13 | print/logging, sırlar, engine sorumlulukları | **DOĞRULANDI / KISMEN** | `logging` yok; stdout (generic.py:126, 147, 521-522; hermes.py:451-453; codex.py:97; base.py:209, 217) vs stderr (claude_code.py:292-293; parallel.py:120); anahtar loglanmıyor ama `Authorization: Bearer` curl argv'de (generic.py:192, hermes.py:166) → `ps` ile görünür; generic.py:169, claude_code.py:138 API hata gövdesi basar | `551a583` logging + redaction; `51ec850` anahtar `-H @dosya` (0600) |

## 4. Yeni bulgular (incelemeyi yürütürken)

| ID | Önem | Bulgu | Kanıt | Durum |
|---|---|---|---|---|
| N1 | **KRİTİK** | CLI bulununca `setup()` generic tarafı başlatmıyor → fallback, `web_fetch` ve `web_search` hep boş. Ağsız kanıt: `CODEX_CLI=/bin/false` → `agent_call` None, `web_fetch` None, `web_search` `[]` | codex.py:58-65 (cursor/gemini/minimax/windsurf/glm :61, kimi :67, copilot :67, amazon_q :44, antigravity :43); generic.py:35-40 | `b92c8ce`: `_init_http_client()` |
| N2 | YÜKSEK | Dashboard: `_last_question` hiç atanmıyor → `panel.sh "soru"` ilk sonuçta `AttributeError`; `f` tuşu olmayan `cycle_filter`'ı çağırır; `s` sahte kaydeder; `stop()` etkisiz | dashboard.py:389-391, 415, 510-513, 111-115 | `45cde65` |
| N3 | ORTA | Dashboard yalnız Scope fazını gösteriyor (engine yalnız ilk faz için `select_phase`; runtime `phase()` override'ları dashboard'a dokunmuyor) | engine.py:58-62; base.py:207-213; generic.py:513-519 | `9693fc3` (engine her faz için bildirir) |
| N4 | ORTA | Claude Code arama DDG yönlendirme linkini (`//duckduckgo.com/l/?uddg=`) açmıyor → engine şemasız URL'yi reddeder | claude_code.py:215-219; engine.py:328 | `c8f1684` |
| N5 | ORTA | Generic önce DDG Instant Answer'a gidiyor (sıradan web sonuçları için güvenilmez; kendi notu bunu söylüyor); HTML arama yalnız curl ile | generic.py:260, 288-299, 303-304; CODEX_CHANGES/web.md:3 | `c8f1684` |
| N6 | ORTA | Doğrulayıcı kaynak metnini görmüyor; "Default to refuted=true if uncertain"; alıntının sayfada geçtiği denetlenmiyor | engine.py:459-466, 361-367 | kısmen: `quoteInSource` (`9693fc3`); kaynak parçası verme **açık** (öneri) |
| N7 | ORTA | JS workflow Python'dan farklı: sabit config (43-46), beraberlik *survives* (205), slot sınırı aşılır (152), `FETCH_PROMPT` içerik vermez (118-119), Node'da `agent/phase/log/pipeline/parallel` tanımsız (22, 249-257), iki dosya aynı `meta.name` (wrapper.js:115-116, workflow.js:29-30) | ilgili satırlar | beraberlik kuralı `51ec850`; kalanı **açık** |
| N8 | DÜŞÜK | `requests` başarısız olunca aynı ücretli çağrı curl ile tekrarlanır; 120 s deadline ile birleşince oylar `None` kalabilir | generic.py:141-143, 474 | `51ec850` |
| N9 | DÜŞÜK | `DR_RUNTIME` doğrulanmaz; bilinmeyen ad sessizce generic | runtime/__init__.py:52-54, 155-157 | `51ec850` (uyarı loglanır) |
| N10 | DÜŞÜK | `CLAUDE_CODE` `=="1"` (runtime/__init__.py:58) vs truthy (parallel.py:28); API base `/v1` farkı (generic.py:97, hermes.py:114 vs claude_code.py:129); `cmd = None` ölü atama (codex.py:80); harness hep dosya yazar (351-359); isim karmaşası (harness.py:98, 196; dashboard.py:133, 536) | ilgili satırlar | **açık** (kozmetik) |
| N11 | — | Ek (bu çalışmada): bir sentez raporu geçerli özet taşıyıp hiçbir doğrulanmış kaynağı citelemediğinde doğrulanmış iddialar sessizce kayboluyordu (`_valid_report` boş `findings` ile de rapor döndürüyordu) | engine.py:404-407 | `be49fc9` (salvage tetiklenir) |

## 5. Eksikler (olması gerekip olmayanlar)

| ID | Eksik | Durum |
|---|---|---|
| E1 | Test/CI yoktu | `2e4ca93` (122 test, 3.9 + 3.12 CI) |
| E2 | Yapılandırılmış logging yoktu | `551a583` |
| E3 | DNS-sonrası IP ve hop başına doğrulama yoktu | `adc74ad` |
| E4 | Alıntı-içerik eşleşmesi yoktu | `9693fc3` (bayrak olarak) |
| E5 | Search/Fetch paralel değildi | `9693fc3` |
| E6 | Capability'ye göre davranış yok (`RuntimeCapabilities` okunmuyor) | **açık** |
| E7 | Claude köprüsünde dönüş kanalı yok | **açık** |
| E8 | CLI'lara non-interaktif bayrak verilmiyor (`codex.py:88-90`; `gh copilot` alt komutsuz) — argümansız stdin'in her CLI'da çalıştığı **doğrulanamadı** | **açık**, gerçek CLI'larla denenmeli |
| E9 | OpenClaw adaptörü / açık hata | dal silindi |
| E10 | README `antigravity` / `_cli_parallel` eksik | düzeltildi |
| E11 | Çalışan araştırmayı iptal mekanizması yok | **açık** (dashboard `stop()` yalnız sonucu atar) |
| E12 | Ortak `stats` şeması yok (engine.py:526-527 vs 516-519) | `9693fc3` (`results.stats`) |
| E13 | Idempotency/önbellek, hız sınırlayıcı, circuit breaker | **açık** (öneri; SYSTEM_DESIGN.md) |

## 6. Fazlalıklar

| ID | Fazlalık | Kanıt | Durum |
|---|---|---|---|
| Z1 | `core/agent.py` (334 satır) | grep → hiç import yok | **silindi** |
| Z2 | `core/web.py` (492 satır) | grep → hiç import yok | **silindi** (SearXNG → `runtime/generic.py`; DDG ayrıştırma → `core/websearch.py`) |
| Z3 | `PipelineMonitor` ve maliyet kayıtları | core/__init__.py:8-9 | **açık** (bağla ya da sil) |
| Z4 | `parallel.py` `pipeline`/`parallel`/`_detect_capability`; hermes dalı no-op (86-89) | parallel.py:24-91 | **açık** (`parallel()` hâlâ marker için duruyor) |
| Z5 | `_RUNTIME_REGISTRY`/`register` | runtime/__init__.py:91-96, 160-175 | gerçek registry oldu |
| Z6 | `RuntimeCapabilities` + 4 enum | base.py:19-157 | **açık** (API riski: `BaseRuntime.capabilities`) |
| Z7 | 10 kopya CLI adaptörü (~1050 satır) | F5d | `runtime/cli.py` (~170 satır) |
| Z8 | 4 JSON / 4+ URL / 4 havuz / 5 payload | F5 | JSON, URL, havuz birleşti; payload **açık** |
| Z9 | `aider.py`, `cline.py` (yalnız isim + mesaj) | aider.py:11-21, cline.py:13-25 | **açık** |
| Z10 | `BaseRuntime.phase` içinde dashboard kodu | base.py:207-213 | kaldırıldı (`551a583`) |
| Z11 | wrapper.js kuyrukları, `parallelCount` | wrapper.js:53-56, 90 | **açık** |
| Z12 | Kök `.env` + `DEEPSEEK_BASE_URL` | .gitignore:3, generic.py:86 | `.env` izlenmiyor ve ignore'da; **anahtarın döndürülmesi önerilir** (içerik bu analizde okunmadı) |
| Z13 | SCOPE_SCHEMA `minItems/maxItems` engine'de eziliyor | schemas.py:14-15, engine.py:254-262 | **açık** |

## 7. Silinen dosyalar ve nedenleri

| Dosya | Neden | Commit |
|---|---|---|
| `core/agent.py` | Hiçbir yerden import edilmiyordu; JSON çıkarma/URL/payload mantığı diğer dosyalarla kopyaydı | `b92c8ce` |
| `core/web.py` | Hiçbir yerden import edilmiyordu; kullanıcıya vadedilen SearXNG yalnız burada vardı (generic'e taşındı), DDG ayrıştırma `core/websearch.py`'a alındı | `b92c8ce` |
| `runtime/codex.py`, `cursor.py`, `gemini.py`, `copilot.py`, `amazon_q.py`, `windsurf.py`, `kimi.py`, `glm.py`, `minimax.py`, `antigravity.py` | Birbirinin neredeyse birebir kopyasıydı (yalnız komut adı/env değişkeni farklı); `runtime/cli.py` içindeki `CliRuntime` + veri alt sınıflarıyla değiştirildi. Sınıf adları (`CodexRuntime` …) `runtime.cli`'den aynen import edilebilir | `b92c8ce` |
| `runtime/_cli_parallel.py` | `core.parallel.run_bounded`'a indirgenmiş tek satırlık sarmalayıcıydı | `b92c8ce` |

Davranış notu: modül yolları `runtime.codex` vb. artık yok (`runtime.cli.CodexRuntime`). `get_runtime("codex")`, `DR_RUNTIME`, `--runtime`, `BaseRuntime` metotları ve `deep_research()`/`print_report()` imzaları korunmuştur.

## 8. Doğrulanamayanlar

- `Bhllcoder1` kullanıcı adı repo içinden doğrulanamadı (git remote küçük harfli `bhllcoder1`); kullanıcının talimatına uyuldu.
- Gerçek web araması, gerçek LLM API'si, DuckDuckGo'nun güncel HTML biçimi ve CLI ajanlarının (codex, gemini, …) stdin davranışı **canlı denenmedi**; testler sahte runtime/çıktı ile yapıldı.
- API hata gövdesinin anahtar içerip içermediği (generic.py:169, claude_code.py:138) doğrulanamadı; log redaksiyonu bunu kapsıyor.
- `.env` dosyasının içeriği bilinçli olarak okunmadı.
