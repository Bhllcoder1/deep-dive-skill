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

**Tüm platformlar — arama (gerçek bir E2E koşusunda ortaya çıktı)**
- DuckDuckGo HTML ucu art arda/eşzamanlı isteğe **bot challenge** (HTTP 202 + "anomaly") döndürüyor; bu, `web_search`'ü boşaltıp LLM'in URL uydurmasına yol açıyordu. Eklenenler: istek aralığı (1,5 sn), challenge algılanınca 300 sn atlama (circuit breaker), anahtarsız **Wikipedia API** yedeği ve isteğe bağlı **Brave Search API** (`BRAVE_API_KEY`, SearXNG ve Brave en güvenilir seçenekler). Sıra: SearXNG → Brave → DDG HTML → Wikipedia → (LLM yedeği, loglu). Wikipedia yedeği dar kapsamlıdır; Türkçe sorgular için `DR_WIKI_LANG=tr`.

**Tüm platformlar — sentez prompt'u (E2E'de ortaya çıktı)**
- Sentez prompt'u çıktı şeklini tarif etmiyordu ("Valid JSON only"); gerçek ajanlar (Hermes) kendi şemasını uydurup sonucu reddettirdi → her seferinde salvage. Düzeltildi; tüm prompt'ların şemadaki zorunlu anahtarları içerdiği testle kilitlendi.

## Kalan sınırlar (doğrulanamadı / açık)
- `cursor`, `copilot`, `amazon_q`: CLI bu makinede kurulu değil; bayraklar satıcı belgesine dayanıyor. Yanlışsa CLI 3 hata sonra atlanır ve API yedeği devreye girer (zarar vermez, yalnız kazanç kaybı). Gerçek makinede `python3 harness.py "..." --runtime cursor --tier low` ile denenmeli.
- `codex` ve `gemini`: sözdizimi kabul edildi ama bu hesaplarda kimlik doğrulama geçersiz (codex: refresh token iptal; gemini: API anahtarı geçersiz) — model yanıtı alınamadı.
- `generic`: gerçek LLM API çağrısı bu makinede ayrıca denenmedi.
- `aider`/`cline`: platform tespit bayrakları (`AIDER_CHAT_MODE`/`AIDER_VERSION`, `CLINE_MCP`) platformlar tarafından ayarlandığı doğrulanamadı.
