# 🦀 bdeepresearch-harness — GitHub Reposu Hazırlama Rehberi

> Popüler açık kaynak projelerden (OpenClaw 383K★, Claude Code 138K★, Omnigent 7.4K★,
> Next.js 141K★, Tailwind 96K★, n8n 197K★) derlenmiş gerçek uygulama örnekleriyle.

---

## İçindekiler

1. [README Hazırlama](#1-readme-hazırlama)
2. [Badge'ler (shields.io)](#2-badge'ler-shieldsio)
3. [Logo & Maskot](#3-logo--maskot)
4. [Web Sitesi & Dokümantasyon](#4-web-sitesi--dokümantasyon)
5. [GitHub Repo Ayarları](#5-github-repo-ayarları)
6. [CI/CD Pipeline](#6-cicd-pipeline)
7. [Lisans](#7-lisans)
8. [Topluluk Yönetimi](#8-topluluk-yönetimi)
9. [Hepsini Birleştirme: Sıfırdan Repo](#9-hepsini-birleştirme-sıfırdan-repo)

---

## 1. README Hazırlama

### 1.1 Banner (Light/Dark Mode)

En profesyonel yöntem — `<picture>` etiketi ile light/dark mod:

```html
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/<USER>/<REPO>/main/assets/banner-light.png">
    <img src="https://raw.githubusercontent.com/<USER>/<REPO>/main/assets/banner-dark.png" alt="bdeepresearch-harness">
  </picture>
</p>
```

Alternatif (daha basit):
```markdown
![Logo (Light)](assets/logo-light.png#gh-light-mode-only)
![Logo (Dark)](assets/logo-dark.png#gh-dark-mode-only)
```

**Boyutlar:** 1200×630px (OG) veya 1280×640px (GitHub Social Preview)
**Araçlar:** Canva (ücretsiz), Figma (ücretsiz), Haikei (ücretsiz SVG)

### 1.2 Başlık & Açıklama

```markdown
<h1 align="center">🦀 bdeepresearch-harness</h1>
<p align="center">
  <em>Universal multi-platform deep research agent — Scope → Search → Fetch → Verify → Synthesize</em>
</p>
<p align="center">
  Works on: <b>Hermes</b> · <b>Claude Code</b> · <b>Kimi Code</b> · <b>Aider</b> · <b>Codex</b> · <b>Cline</b> · <b>Generic Python</b>
</p>
```

### 1.3 Kurulum Komutları (Çoklu Platform)

```markdown
## Quick Start

```bash
# 1. Clone
git clone https://github.com/<USER>/bdeepresearch-harness.git
cd bdeepresearch-harness

# 2. Set API key
export DEEPSEEK_API_KEY="sk-..."

# 3. Run research
python3 harness.py "Your research question"

# Or use pip
pip install requests
python3 harness.py "Research topic" --format json
```

```powershell
# Windows
$env:DEEPSEEK_API_KEY="sk-..."
python3 harness.py "Research topic"
```
```

### 1.4 İçerik Yapısı (Standart Şablon)

```
1. Banner + Badge'ler
2. Kısa açıklama (1-2 cümle)
3. Özellikler (bullet list)
4. Quick Start (kod blokları)
5. Platform Support (tablo)
6. Environment Variables (tablo)
7. Pipeline (Scope→Search→Fetch→Verify→Synthesize)
8. Cost Estimation (tablo)
9. Contributing
10. License
```

### 1.5 Expandable Bölümler

```markdown
<details>
  <summary><b>📖 Table of Contents</b></summary>
  
  1. [README Hazırlama](#1-readme-hazırlama)
  2. [Badge'ler](#2-badge'ler)
  ...
</details>
```

### 1.6 Not/Uyarı Blokları

```markdown
> [!NOTE]
> DeepSeek API requires a free API key from platform.deepseek.com

> [!TIP]
> For best performance, use Claude Code's built-in deep-research workflow

> [!WARNING]
> Web search may be rate-limited. Use SearXNG for production.

> [!IMPORTANT]
> API keys are NEVER logged or stored. Use environment variables only.
```

### 1.7 Emoji Kullanımı

```markdown
🚀 Features      📚 Docs        🔧 Config       💡 Examples
👥 Community     🐛 Issues      ✨ Roadmap      📦 Releases
```

---

## 2. Badge'ler (shields.io)

### 2.1 shields.io URL Yapısı

```
https://img.shields.io/badge/<LABEL>-<MESSAGE>-<COLOR>?style=<STYLE>&logo=<LOGO>&logoColor=<COLOR>
```

### 2.2 Stil Seçenekleri

| Stil | Görünüm | Ne Zaman Kullanılır |
|------|---------|---------------------|
| `for-the-badge` | Büyük, kalın | **OpenClaw stili** — ana badge'ler |
| `flat` | Standart, yuvarlak | Günlük kullanım |
| `flat-square` | Keskin köşeli | Modern görünüm |

### 2.3 Örnek Badge'ler

```markdown
<p align="center">
  <a href="https://github.com/<USER>/bdeepresearch-harness/actions"><img src="https://img.shields.io/github/actions/workflow/status/<USER>/bdeepresearch-harness/ci.yml?branch=main&style=for-the-badge" alt="CI"></a>
  <a href="https://github.com/<USER>/bdeepresearch-harness/releases"><img src="https://img.shields.io/github/v/release/<USER>/bdeepresearch-harness?style=for-the-badge" alt="Release"></a>
  <a href="https://discord.gg/..."><img src="https://img.shields.io/discord/SERVER_ID?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License"></a>
</p>
```

### 2.4 shields.io Dinamik Endpoint'ler

| Badge | URL |
|-------|-----|
| GitHub Stars | `https://img.shields.io/github/stars/<USER>/<REPO>?style=for-the-badge&logo=github` |
| GitHub Release | `https://img.shields.io/github/v/release/<USER>/<REPO>?style=for-the-badge` |
| GitHub Issues | `https://img.shields.io/github/issues/<USER>/<REPO>?style=for-the-badge` |
| GitHub Forks | `https://img.shields.io/github/forks/<USER>/<REPO>?style=for-the-badge` |
| GitHub License | `https://img.shields.io/github/license/<USER>/<REPO>?style=for-the-badge` |
| CI Workflow | `https://img.shields.io/github/actions/workflow/status/<USER>/<REPO>/ci.yml?branch=main&style=for-the-badge` |
| PyPI Version | `https://img.shields.io/pypi/v/<PACKAGE>?style=for-the-badge` |
| Python Version | `https://img.shields.io/pypi/pyversions/<PACKAGE>?style=for-the-badge` |

---

## 3. Logo & Maskot

### 3.1 Seçenekler

| Yaklaşım | Araç | Maliyet | Süre | Örnek |
|----------|------|---------|------|-------|
| **AI ile konsept + vektör** | Midjourney → Figma/Inkscape | $10-60/ay | 1-2 gün | OpenClaw 🦞 |
| **Hazır ikon** | SimpleIcons, SVG Repo | Ücretsiz | 1 saat | - |
| **AI logo üretici** | Looka, Hatchful | $20 tek | 1 saat | Yeni projeler |
| **Minimal metin logosu** | Canva, Figma | Ücretsiz | 30 dk | Claude Code |

### 3.2 Renk Paleti

```markdown
# Önerilen renk paleti (deep-tech teması):
Ana:     #0D1117 (koyu lacivert)
Vurgu:   #58A6FF (parlak mavi)
İkincil: #30363D (gri)
Metin:   #C9D1D9 (açık gri)
Başarı:  #3FB950 (yeşil)
Uyarı:   #D29922 (sarı)
Hata:    #F85149 (kırmızı)
```

**Araçlar:** Coolors.co, Adobe Color

### 3.3 Logo Hosting

```markdown
En iyi yöntem: `assets/` klasörü + `raw.githubusercontent.com`
/assets/logo.svg
/assets/banner-light.png
/assets/banner-dark.png

README'de kullanım:
![Logo](https://raw.githubusercontent.com/<USER>/<REPO>/main/assets/logo.svg)
```

---

## 4. Web Sitesi & Dokümantasyon

### 4.1 Framework Karşılaştırması

| Framework | Öğrenme | İçerik | Arama | AI | Hosting | Maliyet | Kim Kullanır |
|-----------|---------|--------|------|-----|---------|---------|-------------|
| **Mintlify** | 5 dk | .md | ✅ Built-in | ✅ Built-in | Mintlify Cloud | $150/ay | OpenClaw |
| **Next.js** | 2-3 gün | MDX | Ekstra | Ekstra | Vercel | Ücretsiz | Claude Code, Omnigent |
| **Astro** | 1 saat | .md | Ekstra | ❌ | Vercel/Neflify | Ücretsiz | OpenClaw (anasayfa) |
| **GitHub Pages+Jekyll** | 30 dk | .md | ❌ | ❌ | GitHub | Ücretsiz | Küçük projeler |
| **MkDocs** | 15 dk | .md | ✅ Plugin | ❌ | GitHub Pages | Ücretsiz | Python projeleri |

### 4.2 Seçenek 1: GitHub Pages + MkDocs (En Kolay, Ücretsiz)

```bash
# 1. Kur
pip install mkdocs mkdocs-material

# 2. Yeni site oluştur
mkdocs new docs
cd docs

# 3. Yapılandır (mkdocs.yml)
echo 'site_name: bdeepresearch-harness
theme:
  name: material
  palette:
    primary: indigo
  features:
    - search.suggest
plugins:
  - search' > mkdocs.yml

# 4. İçerik yaz
echo "# bdeepresearch-harness" > docs/index.md

# 5. Build
mkdocs build

# 6. Deploy (GitHub Pages)
mkdocs gh-deploy
```

### 4.3 Seçenek 2: Mintlify (Profesyonel, Ama Ücretli)

OpenClaw'un tercihi. `docs.json` yapılandırması:

```json
{
  "global": {
    "brand": {
      "name": "bdeepresearch-harness",
      "primaryColor": "#58A6FF",
      "logo": "/logo.svg"
    },
    "header": {
      "primaryLink": {
        "name": "GitHub",
        "url": "https://github.com/<USER>/bdeepresearch-harness"
      }
    },
    "colors": {
      "primary": "#58A6FF",
      "light": "#79C0FF",
      "dark": "#0D1117"
    }
  },
  "pages": [
    {"group": "Getting Started", "pages": ["quickstart", "installation"]},
    {"group": "Pipeline", "pages": ["scope", "search", "fetch", "verify", "synthesize"]},
    {"group": "Platforms", "pages": ["hermes", "claude-code", "generic-python"]},
    {"group": "API Reference", "pages": ["harness", "monitor"]}
  ]
}
```

### 4.4 Seçenek 3: README-only (En Basit)

Başlangıç için yeterli. İleride docs sitesi eklenir.

---

## 5. GitHub Repo Ayarları

### 5.1 Topics & Description

```bash
gh repo edit <USER>/bdeepresearch-harness \
  --description "Universal multi-platform deep research agent. Scope → Search → Fetch → Verify → Synthesize. Supports Hermes, Claude Code, Kimi Code, generic Python." \
  --add-topic "deep-research" \
  --add-topic "research-agent" \
  --add-topic "multi-platform" \
  --add-topic "adversarial-verification" \
  --add-topic "hermes-agent" \
  --add-topic "claude-code" \
  --add-topic "kimi-code" \
  --add-topic "python"
```

### 5.2 Discussions, Wiki, Projects

| Özellik | Açık/Kapalı | Sebep |
|---------|-------------|-------|
| **Discussions** | ✅ Açık | Soru-cevap, fikir paylaşımı |
| **Wiki** | ❌ Kapalı | Dokümantasyon ayrı sitede |
| **Projects** | ✅ Açık | Roadmap ve task takibi |
| **Sponsors** | ✅ Açık | GitHub Sponsors |

### 5.3 Branch Protection

```yaml
# Settings → Branches → Add rule → main
Branch name pattern: main
☑ Require a pull request before merging
  ☑ Require 1 approval
  ☑ Dismiss stale approvals
☑ Require status checks to pass
  ☑ CI / test (ubuntu-latest, node-20)
  ☑ lint
☑ Require signed commits
☑ Do not allow bypassing
```

### 5.4 Merge Stratejisi

```yaml
Settings → Merge button:
☑ Allow squash merging (DEFAULT)
☐ Allow rebase merging
☐ Allow merge commits
☑ Automatically delete head branches
```

---

## 6. CI/CD Pipeline

### 6.1 GitHub Actions — Temel CI

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check .

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install requests
      - name: Run import test
        run: python3 -c "import sys; sys.path.insert(0,'.'); from runtime import detect; print('Runtime detection:', detect())"
```

### 6.2 Release Automation

`.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: |
            bdeepresearch-harness.tar.gz
```

### 6.3 Security Scan

`.github/workflows/security.yml`:

```yaml
name: Security

on:
  pull_request:
    paths:
      - '.github/workflows/*.yml'
  push:
    branches: [main]

jobs:
  zizmor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install zizmor
      - run: zizmor .github/workflows/*.yml
```

---

## 7. Lisans

### 7.1 Seçenekler

| Lisans | Açıklama | Kim Kullanır |
|--------|----------|-------------|
| **MIT** | En yaygın. Herkes kopyalayabilir, değiştirebilir, satabilir. | OpenClaw, Next.js, Tailwind, Vite |
| **Apache 2.0** | MIT + patent koruması. Şirketler için. | Omnigent |
| **GPL** | Copyleft — türevler de açık kaynak olmalı. | Linux, Git |

**Öneri: MIT** — en basit, en yaygın, en az sorun çıkaran.

### 7.2 LICENSE Dosyası

```markdown
MIT License

Copyright (c) 2026 <NAME>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files...
```

> GitHub'da yeni repo oluştururken "Choose a license" seçeneğinden MIT seçilir.
> Var olan repo için: `gh repo edit <REPO> --add-topic "mit"` + LICENSE dosyası ekle.

---

## 8. Topluluk Yönetimi

### 8.1 Issue Templates

`.github/ISSUE_PROPERTIES/bug_report.yml`:

```yaml
name: Bug Report
description: Report a bug in bdeepresearch-harness
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: "Thanks for reporting!"
  - type: input
    id: version
    attributes:
      label: Version
      placeholder: "e.g., 1.0.0"
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Description
      placeholder: "What happened?"
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Logs
      render: shell
```

`.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Discord
    url: https://discord.gg/...
    about: Ask questions here
```

### 8.2 PR Template

`.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Description
Brief description of changes.

## Related Issue
Closes #...

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor

## Testing
- [ ] Tested with Python 3.10+
- [ ] All existing tests pass

## Checklist
- [ ] Code follows project style
- [ ] Self-review completed
- [ ] No API keys in code
```

### 8.3 CODEOWNERS

`.github/CODEOWNERS`:

```yaml
# Global owners
* @<USER>

# Specific areas
.github/workflows/ @<USER>
docs/ @<USER>
runtime/ @<USER>
```

### 8.4 CONTRIBUTING.md

```markdown
# Contributing to bdeepresearch-harness

## Development Setup

```bash
git clone https://github.com/<USER>/bdeepresearch-harness.git
cd bdeepresearch-harness
pip install requests
export DEEPSEEK_API_KEY="sk-..."
```

## Code Style
- Python 3.10+ type hints
- Follow existing patterns in `runtime/`

## Commit Messages
feat: add new runtime adapter
fix: resolve parallel lock bug
docs: update README badges
```

### 8.5 SECURITY.md

```markdown
# Security Policy

## Supported Versions
| Version | Supported |
|---------|-----------|
| >= 1.0.0 | ✅ |

## Reporting a Vulnerability
Email: <EMAIL>
Do NOT open public issues for security vulnerabilities.
```

### 8.6 Discord Server

1. `discord.com` → Create Server
2. Kanallar: `#general`, `#help`, `#development`, `#releases`
3. GitHub webhook: `Server Settings → Integrations → Webhooks`
4. shields.io badge: `https://img.shields.io/discord/SERVER_ID?style=for-the-badge&logo=discord&logoColor=white`

---

## 9. Hepsini Birleştirme: Sıfırdan Repo

### Adım Adım (Toplam: ~1-2 saat)

```bash
# 1. GitHub'da repo oluştur
gh repo create bdeepresearch-harness --public --description "..." --license MIT

# 2. Clone et
git clone https://github.com/<USER>/bdeepresearch-harness.git
cd bdeepresearch-harness

# 3. Proje dosyalarını koy
cp -r /path/to/your/code/* .

# 4. .gitignore oluştur
echo '__pycache__/
*.pyc
.env
*.tar.gz
.DS_Store
' > .gitignore

# 5. README.md yaz (yukarıdaki şablon)
# 6. LICENSE ekle (MIT)
# 7. .github/ klasörünü oluştur
mkdir -p .github/{workflows,ISSUE_TEMPLATE}

# 8. CI workflow ekle (.github/workflows/ci.yml)
# 9. Issue templates ekle
# 10. CODEOWNERS, CONTRIBUTING.md, SECURITY.md ekle

# 11. Commit & push
git add .
git commit -m "feat: initial release"
git tag v1.0.0
git push origin main --tags

# 12. Repo ayarları (web UI)
# - Topics ekle (gh repo edit)
# - Branch protection (web UI)
# - Discussions aç
# - Sponsor butonu ekle

# 13. (Opsiyonel) GitHub Pages docs sitesi
pip install mkdocs mkdocs-material
mkdocs new docs
mkdocs gh-deploy

# 14. (Opsiyonel) shields.io badge'lerini ekle
```

### Yayın Öncesi Kontrol Listesi

| Öğe | Durum | Açıklama |
|-----|-------|----------|
| README.md | ☐ | Banner, badge'ler, kurulum, özellikler |
| LICENSE | ☐ | MIT seç |
| .gitignore | ☐ | Python standart |
| CI workflow | ☐ | test + lint |
| GitHub Topics | ☐ | deep-research, multi-platform, python |
| Branch Protection | ☐ | main korumalı |
| Discussions | ☐ | Açık |
| Issue Templates | ☐ | Bug report + feature request |
| PR Template | ☐ | Standart |
| CODEOWNERS | ☐ | Seni ekle |
| CONTRIBUTING.md | ☐ | Geliştirme rehberi |
| SECURITY.md | ☐ | Güvenlik politikası |
| shields.io Badge'ler | ☐ | CI, release, license, discord |
| GitHub Pages Docs | ☐ | MkDocs ile |
| Discord Server | ☐ | Topluluk kanalı |
| Twitter/X | ☐ | Duyuru hesabı |
| Sponsor | ☐ | GitHub Sponsors |
