# Platform bazlı inceleme (15 adaptör)

Her platform için: nasıl algılanıyor, ajan çağrısı hangi kanaldan gidiyor, bunu **nasıl doğruladım**, eksik/uyuşmazlık ve karar. İnceleme 2026-10-03'te, çoğu CLI'ın kurulu olduğu bir Linux makinesinde yapıldı.

Doğrulama dereceleri: **E2E** = gerçek bir araştırma baştan sona çalıştırıldı (`--tier low`, gerçek arama + fetch + doğrulama + sentez) · **CANLI** = gerçek CLI'a tek satırlık JSON istemi gönderildi, yanıt ayrıştırıldı · **SÖZDİZİMİ** = bayraklar `--help` ve gerçek çağrıyla kabul edildi ama bu makinedeki hesap/anahtar yüzünden model yanıtı alınamadı · **BELGE** = CLI kurulu değil, bayraklar satıcı belgesine dayanıyor (doğrulanamadı).

## Özet

| # | Platform | Ajan kanalı (varsayılan) | Doğrulama | Durum |
|---|---|---|---|---|
| 1 | `hermes` | `hermes -z <prompt>` (kendi sağlayıcısı, anahtar gerekmez) → API yedeği | **E2E** | ✅ |
| 2 | `claude_code` | `claude -p --tools "" --no-session-persistence --output-format text` (stdin) → API yedeği | **E2E** | ✅ |
| 3 | `generic` | OpenAI-uyumlu API (retry/backoff) | arama/fetch **CANLI**; LLM çağrısı birim testli (bu makinede ayrı anahtar yok) | ✅ |
| 4 | `aider` | generic (Aider'ın kendi CLI'ı kod düzenleyici; kullanılmıyor) | BELGE | ✅ (generic) |
| 5 | `codex` | `codex exec - --skip-git-repo-check -s read-only --ephemeral --color never` (stdin) | **SÖZDİZİMİ** (hesap token'ı iptal edilmiş) | ✅ (hesap yenilenmeli) |
| 6 | `cursor` | `cursor-agent -p --output-format text <prompt>` | BELGE | ⚠ doğrulanamadı |
| 7 | `gemini` | `gemini -p "<yönerge>" -o text` + stdin | **SÖZDİZİMİ** (API anahtarı geçersiz) | ✅ (anahtar yenilenmeli) |
| 8 | `copilot` | `copilot -p <prompt>` | BELGE | ⚠ doğrulanamadı |
| 9 | `amazon_q` | `q chat --no-interactive <prompt>` | BELGE | ⚠ doğrulanamadı |
| 10 | `windsurf` | yok → generic (yalnız `WINDSURF_CLI` ile) | `windsurf` bir editör başlatıcısı | ✅ (generic) |
| 11 | `kimi` | `kimi -p <prompt>` | **E2E** | ✅ |
| 12 | `glm` | yok → generic (yalnız `GLM_CLI` ile) | bilinen headless CLI yok | ✅ (generic) |
| 13 | `minimax` | yok → generic (yalnız `MINIMAX_CLI` ile) | bilinen headless CLI yok | ✅ (generic) |
| 14 | `antigravity` | yok → generic (yalnız `ANTIGRAVITY_CLI` ile) | **CANLI**: `/usr/bin/antigravity` bir VS Code tabanlı editör başlatıcısı | ✅ (generic) |
| 15 | `cline` | generic | BELGE | ✅ (generic) |

## Bulunan uyuşmazlıklar ve kararlar

**Tüm CLI adaptörleri (5-14)**
- *Eski davranış:* prompt, çıplak `codex`/`gemini`/… komutuna stdin'den veriliyordu. Gerçek CLI'lar bu durumda headless çalışmaz (`codex` → `codex exec -`, `gemini` → `-p`, `kimi` → `-p`, TTY bekler) ve fallback'e düşerdi. **Düzeltildi:** her platform için doğru headless bayrakları; prompt `stdin` ya da son argüman (`prompt_mode`).
- *Güvenlik/sağlamlık:* CLI artık **boş geçici dizinde** çalışıyor (ajanlar çalışma dizinini tarar/düzenler; `gemini` `/tmp`'yi tarayıp gürültü üretti), kabuksuz, `max_cli_failures=3` ardışık hatadan sonra CLI o çalıştırma boyunca atlanıyor (her çağrıda 60 sn bekleme yok).
- `windsurf` ve `antigravity` ikilileri **editör başlatıcısı** (`antigravity -` stdin'i bir editör penceresinde açar). Önceki kod bunları ajan CLI'ı sanıp çalıştırıyordu. Artık varsayılan olarak **hiç çalıştırılmıyor**; yalnızca kullanıcı `*_CLI` ile gerçek bir headless komut verirse kullanılıyor. `glm`/`zai`/`minimax` için de bilinen bir headless ajan CLI'ı yok; rastgele bir `zai` ikilisini çalıştırmamak için aynı kural.
- `gh copilot` eski uzantı (suggest/explain), betiklenebilir ajan değil (bu makinede `gh copilot` bilinmeyen komut) → artık denenmiyor; yalnızca bağımsız `copilot -p`.
- Tespit bayrakları (`CODEX_CLI=1` …) bu projenin kendi kuralı; platformlar bunları kendileri ayarlamıyor. Güvenilir seçim: `--runtime X` / `DR_RUNTIME=X`.

**Claude Code**
- Gerçek Claude Code `CLAUDECODE=1` ayarlar; proje `CLAUDE_CODE=1` arıyordu → **otomatik algılama hiç çalışmıyordu**. Düzeltildi (`CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT`, eski `CLAUDE_CODE=1`).
- Köprü yalnız istek gönderiyordu; yanıt kanalı yoktu, `setup()` anahtarsız `True` dönüp her çağrıda `None` veriyordu. Artık gerçek kanal `claude -p` (araçlar kapalı, oturum kaydı yok); anahtar da `claude` da yoksa `setup()` dürüstçe `False`. Kapatmak: `DR_CLAUDE_HEADLESS=0`, komutu değiştirmek: `CLAUDE_CLI`. **Not:** abonelik/kota kullanır.

**Hermes**
- Runtime yalnızca `DEEPSEEK_API_KEY` bulursa çalışıyordu ve anahtarı `~/.hermes/.env` içinde aramıyordu (bu makinede anahtar orada). Artık `hermes -z` (CANLI doğrulandı) birincil kanal, API yedek; `~/.hermes/.env` de okunuyor. Kapatmak: `DR_HERMES_CLI=0`.

**Tüm platformlar — arama (gerçek E2E koşularında ortaya çıktı)**
- DuckDuckGo HTML ucu bot challenge (HTTP 202 "anomaly") döndürüyor; Brave (429), Mojeek, Startpage, Ecosia, Qwant ve halka açık SearXNG örnekleri de bu ağdan engelli/captcha'lı ölçüldü. **Yalnız Bing HTML'i captcha'sız sonuç verdi.** Bu yüzden DuckDuckGo varsayılan zincirden çıkarıldı (`DR_SEARCH_DDG=1` ile opt-in).
- Zincir: **SearXNG** (`SearXNG_URL`/`SEARXNG_URL`) → Brave (`BRAVE_API_KEY`) → **Bing HTML** (yönlendirme linkleri çözülür) → Wikipedia → Google CSE → (LLM yedeği, loglu). Liste kısa kalırsa anahtarsız dikey API'lerle tamamlanır (`core/searchapis.py`: Stack Overflow, Hacker News, OpenAlex; opsiyonel GitHub, arXiv; `DR_SEARCH_VERTICALS`). Hepsi canlı doğrulandı. Yerel SearXNG kurulumu: `docs/tools/setup_searxng.sh`. **IP engelini aşma:** `DR_SEARCH_PROXY=socks5h://127.0.0.1:9050` (Tor, `docs/tools/setup_tor.sh`) ile DuckDuckGo HTML'i tarayıcı UA'sı ile çalışıyor ve zincirin başına geçiyor (canlı: generic ve hermes E2E, alakalı kaynaklar, 0 LLM yedeği). SearXNG'nin kendi DDG motoru Tor üzerinden de 'access denied' verdi, kapalı kaldı. Opsiyonel anahtarlı: `TAVILY_API_KEY`, `SERPER_API_KEY`; opt-in fetch yedeği: `DR_FETCH_JINA=1`.
- **Hermes** için kendi arama backend'i kuruldu: `~/.hermes/config.yaml` → `web.search_backend: searxng`, `~/.hermes/.env` → `SEARXNG_URL=http://127.0.0.1:8888` (yedekler `*.bak.*`). Makinede zaten çalışan `searxng` konteynerinin motorları ayarlandı: DDG/Brave/Startpage kapatıldı (sürekli captcha/limit), bing + google + stackoverflow + github açıldı, `default_lang: all`. Canlı doğrulandı: Hermes'in web aracı ve generic/hermes E2E koşuları doğru kaynağı (Rust Book) buluyor.

**Tüm platformlar — sentez prompt'u (E2E'de ortaya çıktı)**
- Sentez prompt'u çıktı şeklini tarif etmiyordu ("Valid JSON only"); gerçek ajanlar (Hermes) kendi şemasını uydurup sonucu reddettirdi → her seferinde salvage. Düzeltildi; tüm prompt'ların şemadaki zorunlu anahtarları içerdiği testle kilitlendi.

## Kalan sınırlar (doğrulanamadı / açık)
- `cursor`, `copilot`, `amazon_q`: CLI bu makinede kurulu değil; bayraklar satıcı belgesine dayanıyor. Yanlışsa CLI 3 hata sonra atlanır ve API yedeği devreye girer (zarar vermez, yalnız kazanç kaybı). Gerçek makinede `python3 harness.py "..." --runtime cursor --tier low` ile denenmeli.
- `codex` ve `gemini`: sözdizimi kabul edildi ama bu hesaplarda kimlik doğrulama geçersiz (codex: refresh token iptal; gemini: API anahtarı geçersiz) — model yanıtı alınamadı.
- `generic`: gerçek LLM API çağrısı bu makinede ayrıca denenmedi.
- `aider`/`cline`: platform tespit bayrakları (`AIDER_CHAT_MODE`/`AIDER_VERSION`, `CLINE_MCP`) platformlar tarafından ayarlandığı doğrulanamadı.
