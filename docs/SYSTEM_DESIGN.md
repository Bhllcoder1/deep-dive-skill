# Sistem Tasarımı Değerlendirmesi — deep-dive-skill

Kapsam: `feat/architecture-review` dalı. **Baseline** = `d20e154` (dal öncesi), **güncel** = HEAD
(`2e4ca93 … 51ec850`, 11 commit). Baseline referansları `git show d20e154:<dosya>` ile, güncel
referanslar çalışma ağacında `grep -n` / `sed -n` ile doğrulanmıştır. Test paketi HEAD'de
`python3 -m unittest discover -s tests -t .` → **118 test, OK**.

Derecelendirme: ✅ uyuyor · ⚠ kısmen · ❌ uymuyor

---

## 1. Özet tablo

| # | İlke | Baseline (d20e154) | Güncel (HEAD) | Ana değişiklik |
|---|------|:---:|:---:|---|
| 1 | SOLID — S (Tek sorumluluk) | ❌ | ⚠ | 552 satırlık `engine.py` → 57 satırlık orkestratör + `core/phases/*` (9693fc3); `runtime/generic.py` hâlâ çok sorumlu |
| 2 | SOLID — O (Açık/kapalı) | ❌ | ✅ | `register()` + tembel `"module:Class"` kayıt defteri (b92c8ce) |
| 3 | SOLID — L (Liskov) | ❌ | ⚠ | `run_parallel` sözleşmesi adaptörler arasında hâlâ farklı; `RunContext` farkları emiyor |
| 4 | SOLID — I (Arayüz ayrımı) | ⚠ | ⚠ | Değişmedi: 5 soyut metot + soyut `name`; `RuntimeCapabilities` okunmuyor |
| 5 | SOLID — D (Bağımlılık tersine çevirme) | ❌ | ⚠ | `Config` enjekte ediliyor; `core`↔`runtime` paket döngüsü yalnızca tembel `core/__init__` ile yumuşatıldı |
| 6 | DRY | ❌ | ⚠ | Tek JSON ayrıştırıcı, tek URL güvenlik modülü, tek `CliRuntime`; LLM HTTP çağrısı hâlâ 3 kopya |
| 7 | KISS | ❌ | ⚠ | `importlib.reload` + `RLock` kalktı; `RuntimeCapabilities`/`monitor.py` gereksiz karmaşıklık |
| 8 | YAGNI | ❌ | ⚠ | Ölü `core/agent.py`, `core/web.py`, 10 CLI dosyası silindi; `PipelineMonitor`, `parallel()/pipeline()` duruyor |
| 9 | Sorumluluk ayrımı / katmanlama / bağımlılık yönü | ❌ | ⚠ | Faz/bağlam/durum/sonuç katmanları ayrıldı; paylaşılan yardımcılar yanlış pakette (`core`) |
| 10 | Konfigürasyon | ❌ | ✅ | İçe-aktarma anı global'leri + reload → değişmez `core/config.py: Config` |
| 11 | Güvenilirlik (timeout, retry, kısmi hata, idempotency, rate limit, circuit breaker, bütçe) | ❌ | ⚠ | Retry/backoff yalnızca Generic; cache, rate limit, circuit breaker yok; faz bütçesi kooperatif |
| 12 | Ölçeklenebilirlik / eşzamanlılık | ⚠ | ⚠ | Search/Fetch artık paralel; `shutdown(wait=False)` ve maliyet bütçesi yalnızca üst sınır |
| 13a | Güvenlik — prompt injection | ❌ | ⚠ | Fencing + `quoteInSource`; doğrulayıcılar kaynak metni görmüyor, bazı web metinleri çitsiz |
| 13b | Güvenlik — SSRF | ❌ | ⚠ | `urlsafe` + IP-pinned `safefetch`; Generic `requests` yolunda TOCTOU/rebinding penceresi |
| 13c | Güvenlik — shell injection | ❌ | ✅ | `shell=True` kaldırıldı, `shlex` + argv (b92c8ce) |
| 13d | Güvenlik — sırlar | ❌ | ⚠ | `curl -H @file` (0600), log redaksiyonu; LLM API için TLS zorunlu değil |
| 14 | Gözlemlenebilirlik | ❌ | ⚠ | `logging` + stderr + JSON + `run_id` + faz süreleri; metrik/tracing yok |
| 15 | Test edilebilirlik / genişletilebilirlik | ❌ | ✅ | `tests/` (FakeRuntime, 118 test) + CI (2e4ca93) |

---

## 2. İlke bazında değerlendirme

### 2.1 S — Tek Sorumluluk İlkesi — Baseline ❌ → Güncel ⚠

**Kanıt (baseline):**
- `core/engine.py` 552 satır; tek dosyada: içe-aktarma anı konfigürasyonu (`d20e154:core/engine.py:17`, `:34-40`),
  akış (`run`, `:43`), runtime sınır sarmalayıcıları (`_agent_call` `:205`, `_run_parallel` `:222`),
  doğrulama (`_valid_*` `:285-382`), URL güvenliği (`_fetchable_url` `:323`), prompt'lar (`_*_prompt` `:428-469`)
  ve sonuç kurucular (`_empty_result` … `_salvage_result` `:522-541`).

**Kanıt (güncel):**
- `core/engine.py` 57 satır, yalnızca orkestrasyon: `PHASES = (scope, search, fetch, verify, synthesize)` (`core/engine.py:19`), döngü `:43-55`.
- Sorumluluklar ayrı modüllerde: `core/prompts.py`, `core/validate.py`, `core/results.py`, `core/state.py`, `core/context.py`, `core/phases/*.py`.
- Kalan ihlal: `runtime/generic.py` (473 satır) LLM HTTP istemcisi + retry (`:157-174`), 4 arama arka ucu (`:268-395`), sayfa çekme (`:407-459`) ve paralel yürütmeyi (`:461-473`) birlikte taşıyor.

**Etki:** Faz mantığı izole test edilebiliyor (`tests/test_config_pipeline.py`); Generic'teki karışım, alt sınıfların (`CliRuntime`, `AiderRuntime`, `ClineRuntime`) arama/fetch davranışını miras yoluyla zorunlu almasına neden oluyor.

**Öneri:** `generic.py`'yi `LlmClient` (HTTP + retry), `SearchBackends` ve `PageFetcher` bileşenlerine bölüp runtime'larda kompozisyonla kullanmak.

**Durum:** engine bölünmesi **uygulandı (commit 9693fc3)**. Generic bölünmesi **önerilen, uygulanmadı** — 4 alt sınıf miras zincirine dokunur; davranış riski ve kapsam büyük.

### 2.2 O — Açık/Kapalı İlkesi — Baseline ❌ → Güncel ✅

**Kanıt (baseline):** Yeni adaptör için üç yer değişmeliydi: `if/elif` zinciri (`d20e154:runtime/__init__.py:113-156`), algılama zinciri (`:56-84`), harness'ta sabit küme `_RUNTIMES` (`d20e154:harness.py:27`) ve README tablosu.

**Kanıt (güncel):** `register(name, runtime, detect_env)` (`runtime/__init__.py:32-40`), tembel `"module:Class"` yükleme (`:60-64`), yerleşik liste `_BUILTIN` (`:80-99`). Harness seçenekleri kayıt defterinden okunur (`harness.py:21-23`, `:244`). Yeni faz için `core/phases/__init__.py:1-4` sözleşmesi (`NAME` + `run(ctx, state)`) ve `PHASES` demeti.

**Etki:** Yeni adaptör = tek `register()` çağrısı; README güncellemesi yalnızca belgeleme.

**Durum:** **uygulandı (commit b92c8ce)**; faz eklenebilirliği **uygulandı (commit 9693fc3)**.

### 2.3 L — Liskov Yerine Geçme — Baseline ❌ → Güncel ⚠

**Kanıt (baseline):** `run_parallel` hata sözleşmesi farklı: Hermes `TypeError/ValueError` fırlatıyor (`d20e154:runtime/hermes.py:381-385`), Claude Code fırlatmak yerine `[]` / `[None]*n` döndürüyor (`d20e154:runtime/claude_code.py:262-267`), Generic fırlatıyor ve `tuple` kabul ediyor (`d20e154:runtime/generic.py:462-466`).

**Kanıt (güncel) — fark sürüyor:**

| Adaptör | Geçersiz `fn_list` | Geçersiz `max_workers` | `tuple` kabul | Toplu iş timeout'u |
|---|---|---|---|---|
| Generic (+10 CLI, Aider, Cline) | `TypeError` (`runtime/generic.py:464`, `:468`) | `ValueError` (`:466`) | evet (`:463`) | 120 s (`:29`) |
| Hermes | `TypeError` (`runtime/hermes.py:284`, `:286`) | `ValueError` (`:288`) | hayır (`:283`) | 120 s (`:40`) |
| Claude Code | `[]` döner (`runtime/claude_code.py:180`) | `[None]*n` döner (`:185`) | hayır | **yok** (`:191-194`) |

Diğer farklar: retry yalnızca Generic'te (`runtime/generic.py:158-164`); Hermes (`runtime/hermes.py:126-234`) ve Claude Code (`runtime/claude_code.py:97`) tek deneme yapıyor.

**Etki:** Motor bu farkları `RunContext.run_parallel` ile emiyor (istisna yakalama + uzunluk tamamlama, `core/context.py:98-106`), bu yüzden pipeline doğru çalışıyor; ancak `BaseRuntime`'ı doğrudan kullanan üçüncü taraf kod adaptöre göre farklı davranış görür.

**Öneri:** Sözleşmeyi `BaseRuntime.run_parallel` docstring'inde sabitlemek (ör. "fırlatır") ve somut bir `run_parallel` uygulamasını tabana taşımak (bkz. 2.4); Claude Code'a timeout eklemek.

**Durum:** Ortak `run_bounded` primitifi **uygulandı (commit adc74ad)**; sözleşme birleştirmesi **önerilen, uygulanmadı** — Claude Code'un "asla fırlatma" davranışını değiştirmek dış API davranış değişikliği.

### 2.4 I — Arayüz Ayrımı — Baseline ⚠ → Güncel ⚠ (değişmedi)

**Kanıt:** `BaseRuntime` tüm adaptörlere 5 soyut metot + soyut `name` dayatıyor: `name` (`runtime/base.py:165-166`), `setup` (`:174`), `agent_call` (`:180`), `web_search` (`:191`), `web_fetch` (`:197`), `run_parallel` (`:202`). `run_parallel` bir platform yeteneği değil, altyapı işi; her adaptör aynı `run_bounded` çağrısını tekrar yazıyor. `RuntimeCapabilities` (`runtime/base.py:54-158`) 20 alan ve `describe()` (`:140`) tanımlıyor; `capabilities` özelliği (`:170`) hiçbir adaptörde override edilmiyor ve motor/harness tarafından okunmuyor (`grep -rn "capabilities\|describe()"` yalnızca tanımı buluyor).

**Etki:** Yeni adaptör yazarı kullanılmayan bir yetenek modeline ve gereksiz bir paralellik metoduna maruz kalıyor.

**Öneri:** `run_parallel`'ı somut varsayılan (`run_bounded`) yapmak; arayüzü `LlmPort` (agent_call) ve `WebPort` (search/fetch) olarak ayırmak; `RuntimeCapabilities`'i ya kaldırmak ya da motorda kullanmak (ör. `max_parallel_agents` → `max_workers` tavanı).

**Durum:** **önerilen, uygulanmadı** — public `BaseRuntime` API'si; dışarıdaki adaptörleri kırabilir.

### 2.5 D — Bağımlılık Tersine Çevirme — Baseline ❌ → Güncel ⚠

**Kanıt (baseline):** Ayarlar modül global'leri olarak ortamdan okunuyordu (`d20e154:core/engine.py:17`, `:34-40`). `core/__init__.py` motoru hevesle içe aktarıyordu (`d20e154:core/__init__.py:7`) ve `runtime/_cli_parallel.py:5` `core.parallel`'ı içe aktarıyordu → `runtime → core → engine → runtime` döngüsü.

**Kanıt (güncel):** Motor `BaseRuntime` soyutlamasına bağlı (`core/engine.py:17`, `core/context.py:11`) ve `Config` dışarıdan veriliyor (`core/engine.py:22-23`, `:37`). Ancak `runtime/*` hâlâ `core.*` yardımcılarını içe aktarıyor (`runtime/generic.py:14-19`, `runtime/hermes.py:23-28`, `runtime/claude_code.py:15-20`, `runtime/__init__.py:21`, `runtime/base.py:16`), `core` da `runtime`'ı (`core/engine.py:17`, `core/context.py:11`). Döngü yalnızca PEP 562 tembel çözümleme ile kırılıyor (`core/__init__.py:13-31`).

**Etki:** İçe aktarma sırasına duyarlı; `core/__init__.py`'ye hevesli bir import eklemek döngüyü geri getirir.

**Öneri:** Paylaşılan yardımcıları (`jsonparse`, `logs`, `parallel`, `urlsafe`, `safefetch`, `websearch`) daha alt seviyeli bir pakete (ör. `deepdive_common/` veya `util/`) taşımak; yön `core → runtime → util` olur.

**Durum:** Config enjeksiyonu **uygulandı (commit 9693fc3)**, tembel `core/__init__` **uygulandı (commit 551a583)**; paket taşıma **önerilen, uygulanmadı** — tüm import yollarını değiştirir, dış kullanıcılar `core.urlsafe` vb. yollarına bağlı olabilir.

### 2.6 DRY / KISS / YAGNI

| Konu | Baseline | Güncel | Durum |
|---|---|---|---|
| JSON ayrıştırıcı | 4 kopya: `d20e154:core/agent.py:44`, `runtime/claude_code.py:155`, `runtime/generic.py:225`, `runtime/hermes.py:243` | Tek: `core/jsonparse.py:20` | uygulandı (adc74ad) |
| URL güvenliği | 3 kopya: `d20e154:core/engine.py:323`, `runtime/generic.py:435`, `runtime/hermes.py:286` | Tek: `core/urlsafe.py` | uygulandı (adc74ad) |
| CLI adaptörleri | 10 dosya × ~113 satır, aynı `run_parallel` (ör. `d20e154:runtime/gemini.py:110`, `runtime/cursor.py:110`) | Tek `CliRuntime` + 10 veri sınıfı (`runtime/cli.py:28-167`) | uygulandı (b92c8ce) |
| DDG HTML ayrıştırıcı | adaptör başına | `core/websearch.py` | uygulandı (c8f1684) |
| LLM HTTP çağrısı (payload + uç nokta + yanıt ayrıştırma) | 3 kopya | **hâlâ 3 kopya**: `runtime/generic.py:144-155`, `runtime/hermes.py:149-159`, `runtime/claude_code.py:109-119`; uç nokta varsayılanları farklı (`generic.py:113` `…/v1`, `claude_code.py:121` `/v1`'siz) | önerilen, uygulanmadı |
| API anahtarı bulma (`~/.env`) | 2 kopya | hâlâ 2: `runtime/generic.py:99-109`, `runtime/hermes.py:67-109` | önerilen, uygulanmadı |
| KISS: konfigürasyon | `os.environ` yazma + `importlib.reload` + `RLock` (`d20e154:harness.py:31`, `:90`, `:191`, `:222`) | `Config.resolve()` (`harness.py:114`) | uygulandı (9693fc3) |
| YAGNI: ölü modüller | `core/agent.py` (334), `core/web.py` (492) hiçbir yerden içe aktarılmıyordu | silindi | uygulandı (b92c8ce) |
| YAGNI: kalanlar | — | `PipelineMonitor` (`core/monitor.py:326`) kullanılmıyor (yalnızca `ModelConfig`, `core/dashboard.py:336`); `parallel()`/`pipeline()`/`_detect_capability` (`core/parallel.py:24-91`) hiçbir yerden çağrılmıyor; `RuntimeCapabilities` (bkz. 2.4); `logs.run_adapter` (`core/logs.py:67`) kullanılmıyor; `runtime._dashboard` atanıyor ama okunmuyor (`harness.py:69`) | önerilen, uygulanmadı |

**Etki:** LLM çağrısının 3 kopyası, retry/TLS/timeout politikasının adaptörlere göre ayrışmasının (bkz. 2.3, 2.9) kök nedeni.

**Öneri:** Tek `LlmClient` (Generic'teki retry'lı uygulama) ve Hermes/Claude Code'un bunu kullanması.

**Neden uygulanmadı:** Hermes'in curl-only yolu ve Claude Code'un `requests`-only yedek yolu kasıtlı farklılıklar; birleştirme ağ davranışını değiştirir, ayrı commit ve test gerektirir.

### 2.7 Sorumluluk ayrımı / katmanlama / bağımlılık yönü — Baseline ❌ → Güncel ⚠

**Güncel katmanlar:**

```
harness.py (CLI/API, rapor çıktısı)
   └─ core/engine.py (orkestratör, PHASES)
        ├─ core/phases/*.py (iş mantığı)  ── core/prompts.py, core/validate.py, core/results.py
        ├─ core/context.py (RunContext: runtime sınırı, sayaç, bütçe, süre)
        ├─ core/state.py (RunState), core/config.py (Config)
        └─ runtime/ (BaseRuntime + adaptörler)
             └─ core/{jsonparse,logs,parallel,urlsafe,safefetch,websearch}.py   ← yanlış paket
```

**Kanıt:** Fazlar runtime'a yalnızca `RunContext` üzerinden dokunuyor (`core/context.py:15-16`, `:60-107`); istisnalar sınırda yutuluyor (`:64-68`, `:70-76`, `:78-84`). İhlal: aşağı katman (`runtime`) üst paketin (`core`) yardımcılarına bağlı (bkz. 2.5). Ayrıca `synthesize` fazı orkestratörün işi olan `ctx.end_phase()`'i kendisi çağırıyor (`core/phases/synthesize.py:14`, `:21`) — süre sonuç sözlüğüne girsin diye; zararsız (ikinci çağrı no-op, `core/context.py:39-42`) ama sorumluluk sızıntısı.

**Durum:** katmanlar **uygulandı (commit 9693fc3)**; paket yönü **önerilen, uygulanmadı** (bkz. 2.5).

### 2.8 Konfigürasyon — Baseline ❌ → Güncel ✅

**Kanıt (baseline):** Ayarlar içe-aktarma anında global'lere okunuyordu (`d20e154:core/engine.py:17`, `:34-40`); harness çağrı başına `os.environ`'u değiştirip (`d20e154:harness.py:90`) motoru `importlib.reload` ile yeniden yüklüyor (`:191`), sonra geri yüklüyordu (`:222`); eşzamanlı çağrılar `RLock` ile seri hale getiriliyordu (`:31`).

**Kanıt (güncel):** `@dataclass(frozen=True) class Config` (`core/config.py:24-48`); katı `resolve()` (`:51-70`, harness API'si için `ValueError`) ve hoşgörülü `from_env()` (`:72-87`); doğrulama `__post_init__` (`:38-48`). Motor `config or Config.from_env()` alıyor (`core/engine.py:37`); global durum yok.

**Etki:** Eşzamanlı, farklı ayarlı çalıştırmalar güvenli; testler ortam değişkeni değiştirmeden yapılandırabiliyor.

**Durum:** **uygulandı (commit 9693fc3)**. Not: runtime tarafı ayarları (`LLM_API_BASE`, `LLM_MODEL`, timeout sabitleri, `_API_RETRIES`) hâlâ `os.environ` ve modül sabitlerinden okunuyor (`runtime/generic.py:24-33`, `:113`, `:145`) — `Config` kapsamı dışında; **önerilen, uygulanmadı**.

### 2.9 Güvenilirlik — Baseline ❌ → Güncel ⚠

| Mekanizma | Baseline | Güncel | Kanıt (güncel) | Durum |
|---|---|---|---|---|
| I/O timeout'ları | Var ama tutarsız (Claude Code fetch `--max-time 30`, bazı yerlerde yok) | Her HTTP/curl çağrısında bağlantı + toplam timeout | `runtime/generic.py:24-29`, `core/safefetch.py:47-49`, `:79` | uygulandı (adc74ad) |
| Toplu paralel timeout | yok | Generic/Hermes 120 s; **Claude Code yok** | `runtime/generic.py:470`, `runtime/hermes.py:290`, `runtime/claude_code.py:191-194` | kısmen |
| Retry + üstel backoff + jitter | Yalnızca ölü `core/agent.py:282`, `:287` | **Yalnızca Generic** (+ ondan türeyenler); 2 ek deneme, 1–8 s | `runtime/generic.py:30-33`, `:158-174` | uygulandı (51ec850); Hermes/Claude Code önerilen |
| Kısmi hata toleransı | Verify batch'leri | Her runtime çağrısı `None`'a dönüşüyor; uzunluk korunuyor; sentez başarısızsa `salvage` | `core/context.py:61-107`, `core/phases/synthesize.py:22`, `core/results.py:63-70` | uygulandı (9693fc3) |
| Faz bütçesi | yok | `Config.phase_budget_s` (varsayılan 900 s); **kooperatif**: yalnızca batch'ler arasında kontrol, çalışan batch kesilmez; Scope/Synthesize tek çağrı olduğu için etkisiz | `core/config.py:21`, `:36`; `core/context.py:44-45`, `:94-97` | uygulandı (9693fc3) |
| İdempotency / cache | yok | **yok** — aynı soru her seferinde tüm çağrıları yeniden yapar | — | önerilen, uygulanmadı |
| Rate limiting | yok | **yok** — DDG HTML ve LLM API'ye `max_workers` kadar eşzamanlı istek | — | önerilen, uygulanmadı |
| Circuit breaker | yok | **yok** — API çökmüşken her çağrı 3 deneme × backoff harcar | — | önerilen, uygulanmadı |

**Ek bulgu (açık):** CLI bulunduğunda `CliRuntime.setup()` API anahtarı/URL'si olmadan `_ready = True` yapıyor (`runtime/cli.py:82-86`). CLI başarısız olunca Generic'e düşülüyor (`:98`); `_api_url` boş olduğu için `requests` `MissingSchema` fırlatıyor, bu da "geçici" sayılıp (`runtime/generic.py:194-196`) iki kez backoff ile yeniden deneniyor (yerelde doğrulandı: `_post_once` → `(None, True)`). Sonuç doğru (`None`) ama her başarısız CLI çağrısı ~1,5–4,5 s boşa bekliyor.

**Neden uygulanmadı:** Cache/rate limit/circuit breaker yeni durum ve konfigürasyon yüzeyi getirir (kapsam); Hermes/Claude Code retry'ı bunların ağ yollarını değiştirir (davranış riski).

### 2.10 Ölçeklenebilirlik / eşzamanlılık — Baseline ⚠ → Güncel ⚠

**Kanıt (baseline):** Yalnızca Verify paraleldi (`d20e154:core/engine.py:152`); Search (`:81`) ve Fetch (`:109`) sıralı döngülerdi.

**Kanıt (güncel):**
- Search ve Fetch paralel: `core/phases/search.py:32`, `core/phases/fetch.py:31` (**uygulandı, commit 9693fc3**).
- Sınırlı işçi: `RunContext.run_parallel` batch'leri `cfg.max_workers` ile böler, runtime sınırı yok saysa bile (`core/context.py:86-99`); sert tavan `HARD_MAX_WORKERS = 20` (`core/tiers.py:43`), `Config` doğrular (`core/config.py:47-48`).
- Maliyet bütçesi yalnızca üst sınır: tier formülü (`core/tiers.py:4`) mantıksal çağrıları sayar; retry'lar (×3'e kadar, `runtime/generic.py:30`) ve CLI→Generic yedeği gerçek HTTP çağrısı sayısını artırır, `stats.agentCalls` (`core/results.py:38`) bunları görmez. Gerçek token/USD bütçesi yok.
- `run_bounded` `executor.shutdown(wait=False, cancel_futures=True)` (`core/parallel.py:126`): sıradaki işler iptal edilir, ama timeout'a uğrayan **çalışan** işler arka planda sürer. `ThreadPoolExecutor` işçileri daemon değildir ve Python çıkışta onları join eder → süreç çıkışı en uzun I/O timeout'u kadar gecikebilir ve bu işler kota tüketmeye devam eder. Buna karşılık dashboard iş parçacığı daemon'dır (`harness.py:82`) ve çıkışta sessizce öldürülür.
- Batch modeli: bir batch'in en yavaş işi tüm batch'i bekletir (`core/context.py:92-99`); sürekli kayan pencere yok.
- `rt.run_id` runtime **örneğine** yazılıyor (`core/engine.py:39`); aynı runtime örneği iki eşzamanlı çalıştırmada paylaşılırsa log'lardaki `run_id` karışır.

**Öneri:** Kayan pencere (tek executor, `max_workers` semafor), `RunContext` içinde `threading.Event` ile kooperatif iptal, `run_id`'yi `RunContext` → logger adapter ile taşımak.

**Durum:** paralel Search/Fetch **uygulandı (9693fc3)**; diğerleri **önerilen, uygulanmadı** — yürütme modelini değiştirir, zamanlama testleri gerektirir.

### 2.11 Güvenlik

#### a) Prompt injection — Baseline ❌ → Güncel ⚠

**Uygulanan (commit 9693fc3):** Web kaynaklı metin `<untrusted_*>` ile çitleniyor ve çiti kapatma girişimleri siliniyor (`core/prompts.py:6-12`); talimat bildirimi (`:15-18`); kaynak metin (`:47`), doğrulanan iddia (`:56`) ve onaylanan iddialar (`:69-71`) çitli. Alıntı sayfada birebir yoksa `quoteInSource=False` (`core/phases/fetch.py:22`), doğrulayıcıya uyarı eklenir (`core/prompts.py:58-59`) ve sıralamada geriye itilir (`core/phases/fetch.py:39-42`). Sentez yalnızca doğrulanmış kaynakları atıf olarak kabul eder (`core/phases/synthesize.py:20`).

**Açık kalan:**
- Doğrulayıcılar **kaynak metni almıyor** (`core/prompts.py:52-63`): yalnızca iddia + alıntı + URL; "çürüt" kararı modelin kendi bilgisine dayanıyor. Öneri: ilgili kaynak alıntısını (±N karakter) çitli olarak vermek.
- Çitsiz web kaynaklı metin: çürütülen/doğrulanamayan iddialar sentez prompt'una çitsiz giriyor (`core/prompts.py:74-79`); arama sonucu başlığı fetch prompt'unda çitsiz (`core/prompts.py:43`).

**Neden uygulanmadı:** Doğrulayıcıya kaynak vermek token maliyetini ve oy dağılımını değiştirir (davranış riski, değerlendirme gerektirir).

#### b) SSRF — Baseline ❌ → Güncel ⚠

**Baseline:** Claude Code fetch yalnızca şema kontrolüyle `curl -sL` (`d20e154:runtime/claude_code.py:227-242`); Hermes `curl -L` ile yönlendirmeleri doğrulamadan izliyordu (`d20e154:runtime/hermes.py:353`); DNS kontrolü hiçbir yerde yoktu.

**Güncel (commit adc74ad):** Sözdizimsel kapı — şema, kimlik bilgisi, localhost, özel/rezerve IP, belirsiz sayısal host (`core/urlsafe.py:39-67`); DNS kapısı — tüm adresler public olmalı (`:77-101`); `safefetch` her sıçramada doğrulayıp `curl --resolve` ile IP'yi sabitler, yönlendirmeleri elle izler (`core/safefetch.py:59-92`, pin `:69`, `:74`). Hermes ve Claude Code bu yolu kullanıyor (`runtime/hermes.py:274`, `runtime/claude_code.py:173`).

**Açık kalan:** Generic'in `requests` yolu (`runtime/generic.py:418-453`) yalnızca bağlantıdan **önce** DNS kontrolü yapıyor (`:409`, her sıçrama `:431`), sonra `requests.get` adı yeniden çözüyor (`:423`) → TOCTOU / DNS rebinding penceresi. SearXNG adresi operatör tanımlı olduğu için bilinçli olarak kontrol dışı (`runtime/generic.py:286-294`).

**Öneri:** `requests` yolunu IP'ye sabitlemek (çözülen IP'ye bağlanıp `Host` başlığı + SNI ayarlayan transport adapter) veya Generic'te de `fetch_text_with_curl` kullanmak.

**Neden uygulanmadı:** Özel `requests` adapter'ı TLS/SNI davranışını değiştirir; curl'e geçiş `requests` olan ama curl olmayan ortamları kırar.

#### c) Shell injection — Baseline ❌ → Güncel ✅

**Baseline:** 10 CLI adaptöründe `shell=True` (ör. `d20e154:runtime/codex.py:86`, `runtime/copilot.py:90`, `runtime/kimi.py:92`); `*_CLI` değeri doğrudan kabukta çalışıyordu. `panel.sh` soruyu `python -c` içine gömüyordu.

**Güncel:** `shlex.split` + çalıştırılabilir doğrulaması, kabuksuz argv (`runtime/cli.py:56-75`, `:103-104`); prompt stdin ile. **Uygulandı (commit b92c8ce; panel.sh 9ce69b7)**.

#### d) Sırlar — Baseline ❌ → Güncel ⚠

**Baseline:** Bearer anahtarı curl argv'sinde, `ps` ile okunabilir (`d20e154:runtime/generic.py:192`, `runtime/hermes.py:166`).

**Güncel:** Başlıklar 0600 geçici dosyada, `curl -H @file` (`core/safefetch.py:18-34`; kullanım `runtime/generic.py:222-228`, `runtime/hermes.py:166-173`) — **uygulandı (51ec850)**. Log redaksiyonu (Bearer, `sk-…`, `api_key=`, query token'ları) `core/logs.py:19-31`, formatter `:34-47` — **uygulandı (551a583)**. Hata log'ları istisna metni yerine tür adını yazar (`runtime/generic.py:195`).

**Açık kalan:**
- LLM API anahtarı yapılandırılan her `LLM_API_BASE`'e gönderiliyor; `http://` kabul ediliyor (`runtime/generic.py:116`, `runtime/hermes.py:122`), Claude Code yedeği URL'yi hiç doğrulamıyor (`runtime/claude_code.py:121`) → TLS zorunlu değil.
- Redaksiyon yalnızca `ensure_configured()`'ın kurduğu handler'da; uygulama `deepdive` logger'ını kendisi yapılandırmışsa devre dışı (`core/logs.py:57-58`).

**Öneri:** `http://` yalnızca loopback için (ya da `DR_ALLOW_INSECURE_LLM=1` ile) izinli olsun; redaksiyonu handler yerine `logging.Filter` olarak logger'a eklemek.

**Neden uygulanmadı:** Yerel `http://` LLM sunucusu (Ollama, vLLM) kullanan kurulumları kırabilir — davranış riski.

### 2.12 Gözlemlenebilirlik — Baseline ❌ → Güncel ⚠

**Baseline:** Dağınık `print`; bazıları stdout'a yazarak JSON çıktısını bozuyordu (ör. `d20e154:runtime/generic.py:48`, `runtime/hermes.py:50`, `harness.py:195-199`).

**Güncel (commit 551a583):** Tek `deepdive` logger ağacı, yalnızca stderr, `DR_LOG_LEVEL`, `DR_LOG_FORMAT=json` (`ts`, `level`, `logger`, `run_id`) (`core/logs.py:1-64`); `run_id` her sonuca girer (`core/results.py:33`) ve runtime log'larına taşınır (`core/engine.py:39`, `runtime/base.py:208-217`); faz süreleri `stats.phaseSeconds` (`core/results.py:39`, `core/context.py:35-42`); `searchFallbacks`, `agentCalls` sayaçları (`core/results.py:38`). `harness.print_report` (`harness.py:152-231`) kasıtlı olarak stdout'a yazar (rapor çıktısı); JSON modunda ilerleme stderr'e yönlendirilir (`harness.py:287-289`).

**Açık kalan:** `core/parallel.py:51`, `:82`, `:146-147` hâlâ `print` kullanıyor (redaksiyonsuz; `:146` istisna metnini yazar); Claude Code köprü işaretleri bilinçli `print` (`runtime/claude_code.py:66`). Metrik uç noktası (Prometheus/OTel), tracing span'leri, çağrı başına gecikme histogramı ve token/maliyet ölçümü yok.

**Öneri:** `core/parallel.py`'yi logger'a geçirmek; faz/agent çağrısı başına OpenTelemetry span'i (isteğe bağlı bağımlılık).

**Durum:** logging **uygulandı (551a583)**; metrik/tracing **önerilen, uygulanmadı** — yeni bağımlılık ve kapsam.

### 2.13 Test edilebilirlik / genişletilebilirlik — Baseline ❌ → Güncel ✅

**Baseline:** Test paketi ve CI yoktu (`tests/` ve `.github/workflows/ci.yml` 2e4ca93'te eklendi).

**Güncel:** `tests/fakes.py:24` `FakeRuntime` (betikli arama/sayfa/çıkarım/oy/sentez); 10 test modülü, 118 test (motor, config/pipeline, harness, CLI runtime, generic runtime, kayıt defteri, paylaşılan modüller, log, dashboard, panel.sh). Enjeksiyon noktaları: `Config`, `runtime=` parametresi (`core/engine.py:22`), `resolver`/`runner` parametreleri (`core/urlsafe.py:77`, `core/safefetch.py:50-51`), `register()` (`runtime/__init__.py:32`).

**Açık kalan:** Hermes ve Claude Code runtime'ları için ayrı birim testi yok (`ls tests/` → `test_hermes*`, `test_claude_code*` yok); `core/monitor.py` (738 satır) testsiz.

**Durum:** **uygulandı (commit 2e4ca93, sonraki commit'lerde genişletildi)**.

---

## 3. Sistem tasarımı kurallarına uymayan ve hâlâ açık kalanlar (öncelik sırasıyla)

| Öncelik | Konu | Kanıt | Risk |
|:---:|---|---|---|
| P1 | Generic `requests` fetch yolunda DNS rebinding / TOCTOU | `runtime/generic.py:409`, `:423`, `:431` | SSRF ile iç ağ erişimi |
| P1 | LLM API anahtarı TLS'siz uç noktaya gidebilir; Claude Code yedeği URL'yi doğrulamıyor | `runtime/generic.py:116`, `runtime/hermes.py:122`, `runtime/claude_code.py:121` | Anahtar sızıntısı |
| P1 | Doğrulayıcılar kaynak metni görmüyor; sentezde çitsiz web metni | `core/prompts.py:52-63`, `:74-79`, `:43` | Doğrulama kalitesi, prompt injection |
| P2 | Rate limiting ve circuit breaker yok | — (Generic retry `runtime/generic.py:158-164` her çağrıda tekrar dener) | DDG engeli, API kotası tükenmesi |
| P2 | Retry yalnızca Generic'te; Claude Code'da toplu timeout yok | `runtime/hermes.py:126-234`, `runtime/claude_code.py:191-194` | Tutarsız dayanıklılık |
| P2 | CLI başarısız → boş URL ile Generic'e düşüş, "geçici" sayılıp yeniden deneme | `runtime/cli.py:82-86`, `runtime/generic.py:194-196` | Boşa bekleme |
| P2 | `run_parallel` sözleşmesi adaptörler arasında farklı (LSP) | `runtime/generic.py:463-468`, `runtime/hermes.py:283-288`, `runtime/claude_code.py:178-185` | Doğrudan kullanımda sürpriz |
| P2 | `core` ↔ `runtime` paket döngüsü | `core/engine.py:17`, `runtime/generic.py:14-19`, `core/__init__.py:13-31` | İçe aktarma kırılganlığı |
| P3 | Faz bütçesi kooperatif; iptal yok; timeout'lu işler arka planda sürer | `core/context.py:94`, `core/parallel.py:126` | Süre/kota aşımı |
| P3 | İdempotency / yanıt önbelleği yok | — | Tekrarlı maliyet |
| P3 | LLM HTTP çağrısı 3 kopya; `~/.env` okuma 2 kopya (DRY) | `runtime/generic.py:144-155`, `runtime/hermes.py:149-159`, `runtime/claude_code.py:109-119` | Politika sapması |
| P3 | Ölü/kullanılmayan: `PipelineMonitor`, `RuntimeCapabilities`/`describe`, `parallel()`/`pipeline()`, `logs.run_adapter`, `runtime._dashboard` | `core/monitor.py:326`, `runtime/base.py:54-158`, `core/parallel.py:24-91`, `core/logs.py:67`, `harness.py:69` | Bakım yükü (YAGNI) |
| P3 | `run_id` runtime örneğinde paylaşılıyor | `core/engine.py:39` | Eşzamanlı çalıştırmada log karışması |
| P3 | `core/parallel.py` hâlâ `print` ile log; metrik/tracing yok | `core/parallel.py:51`, `:82`, `:146-147` | Gözlemlenebilirlik açığı |
| P3 | Claude Code köprüsü yalnızca istek gönderiyor, yanıt kanalı yok | `runtime/claude_code.py:93-95` | "Native" mod fiilen DeepSeek yedeği |

---

## 4. Hedef Mimari

Mevcut HEAD hedefin büyük kısmını uyguluyor; aşağıdaki tasarım güncel durumu ve kalan adımları birlikte gösterir.

```
harness.py ── Config.resolve(kwargs) ──► core/engine.run(question, runtime, config)
                                          │
                                          ├─ RunContext(rt, cfg, question, run_id)   core/context.py
                                          ├─ RunState(question)                       core/state.py
                                          └─ for phase in PHASES: phase.run(ctx, state)
                                                PHASES = (scope, search, fetch, verify, synthesize)
                                                core/phases/{scope,search,fetch,verify,synthesize}.py
                                                   ├─ core/prompts.py   (çitleme)
                                                   ├─ core/validate.py  (şema/alan doğrulama)
                                                   └─ core/results.py   (sonuç sözlükleri)
runtime/__init__.py  register()/get_runtime()/detect()   ← gerçek kayıt defteri
   ├─ base.py        BaseRuntime (ABC)
   ├─ generic.py     GenericRuntime (OpenAI-uyumlu API + retry, arama, fetch)
   ├─ cli.py         CliRuntime + 10 veri sınıfı (Codex, Cursor, Gemini, …)
   ├─ hermes.py, claude_code.py, aider.py, cline.py
paylaşılan yardımcılar (bugün core/ altında):
   core/jsonparse.py  tek JSON ayrıştırıcı
   core/urlsafe.py    tek URL güvenlik kapısı (sözdizimsel + DNS)
   core/safefetch.py  IP-sabitli, sıçrama-doğrulamalı curl fetch + sır başlık dosyası
   core/websearch.py  tek DDG HTML ayrıştırıcı
   core/parallel.py   run_bounded (tek sınırlı paralel primitif)
   core/logs.py       logging, redaksiyon, JSON, run_id
```

| Bileşen | Desen | Durum |
|---|---|---|
| `Config` (değişmez, `resolve`/`from_env`/`replace`) | Value Object, açık enjeksiyon | uygulandı (9693fc3) |
| Faz modülleri (`NAME` + `run(ctx, state)`), `PHASES` demeti | Pipeline + Strategy | uygulandı (9693fc3) |
| `RunContext` — runtime'a tek erişim noktası, istisna sınırı, sayaç, bütçe | Facade / Anti-corruption layer | uygulandı (9693fc3) |
| Runtime kayıt defteri (`register`, tembel `"module:Class"`, `detect_env`) | Registry + Plugin | uygulandı (b92c8ce) |
| Ortak `CliRuntime` (veri odaklı alt sınıflar, kabuksuz argv) | Template Method | uygulandı (b92c8ce) |
| Tek URL güvenlik modülü (`urlsafe` + `safefetch`) | Tek politika noktası | uygulandı (adc74ad); Generic `requests` yolu hariç |
| Tek JSON ayrıştırıcı (`jsonparse`) | DRY | uygulandı (adc74ad) |
| Logging tabanlı gözlemlenebilirlik (`logs`) | Yapılandırılmış log | uygulandı (551a583) |

### Sonraki adımlar (önerilen, uygulanmadı)

1. **Paket döngüsünü kaldırmak:** `jsonparse`, `logs`, `parallel`, `urlsafe`, `safefetch`, `websearch`'ü `core` dışında alt seviyeli bir pakete taşımak; `core/__init__.py`'deki tembel çözümleme koruma olmaktan çıkar. (Import yolu değişikliği — dış kullanıcıları etkiler.)
2. **Doğrulayıcılara kaynak alıntısı vermek:** `prompts.verify` çağrısına ilgili kaynak parçasını çitli olarak eklemek; çürütülen/doğrulanamayan iddiaları ve başlıkları da çitlemek.
3. **İstek yolunda IP sabitleme:** Generic `requests` fetch'ini çözülen IP'ye sabitleyen transport adapter'ı veya `fetch_text_with_curl`'e yönlendirme.
4. **Kooperatif iptal:** `RunContext` içinde `threading.Event`; bütçe dolunca veya `KeyboardInterrupt`'ta set edilir, fazlar ve runtime çağrıları kontrol eder; kayan pencere yürütücü.
5. **Circuit breaker + token-bucket rate limiter:** host/API başına (DDG, Google, LLM uç noktası); `RunContext` veya ortak `LlmClient` seviyesinde.
6. **Disk üzerinde yanıt önbelleği:** `(url, prompt hash)` anahtarlı, TTL'li; tekrar çalıştırmada idempotency ve maliyet düşüşü.
7. **`RuntimeCapabilities`'i kaldırmak ya da kullanmak:** ör. `max_parallel_agents` → `max_workers` tavanı, `has_builtin_web_search` → arama stratejisi seçimi; `run_parallel`'ı `BaseRuntime`'da somut varsayılan yapmak.
8. **`core/monitor.py` `PipelineMonitor`'ü bağlamak veya silmek:** yalnızca `ModelConfig` kullanılıyor (`core/dashboard.py:336`).
9. **Tek `LlmClient`:** retry/backoff, TLS politikası ve uç nokta normalizasyonu tek yerde; Hermes ve Claude Code yedeği bunu kullanır; `CliRuntime` yedeği API anahtarı yoksa denemeden `None` döner.
10. **Claude Code köprüsü yalnızca istek gönderiyor** (`runtime/claude_code.py:93-95`): ya JS wrapper'dan yanıt kanalı (ör. stdin/FIFO üzerinden JSON) eklenmeli ya da "native" iddiası belgelerden kaldırılmalı.
11. **Gözlemlenebilirlik:** `core/parallel.py` `print`'lerini logger'a taşımak; isteğe bağlı OpenTelemetry span'leri ve token/maliyet metrikleri; `run_id`'yi runtime örneği yerine çağrı bağlamıyla taşımak.
