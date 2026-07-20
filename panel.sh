#!/bin/bash
# deep-dive-skill — Kontrol Paneli Başlatıcı
# Bu script'i kendi terminalinde çalıştır, panel açılsın.
# 
# Kullanım:
#   ./panel.sh                    # Panel aç
#   ./panel.sh "araştırma sorusu" # Pipeline + Panel

cd "$(dirname "$0")"

# API key kontrol
if [ -z "$DEEPSEEK_API_KEY" ]; then
    if [ -f ~/.bashrc ]; then
        source ~/.bashrc
    fi
fi

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ DEEPSEEK_API_KEY bulunamadı."
    echo "  export DEEPSEEK_API_KEY='sk-...'"
    exit 1
fi

echo "━━━ Deep Dive Skill Control Panel ───"
echo "  ↑↓ navigate · r research · h history · m model · q quit"
echo ""

if [ -z "$1" ]; then
    # Sadece panel aç
    python3 -m core.dashboard
else
    # Pipeline + Panel
    python3 -c "
from core.dashboard import Dashboard
from harness import deep_research
import threading, time

dash = Dashboard()
dash.subtitle = '$1'

def run_pipeline():
    result = deep_research('$1', show_dashboard=False)
    dash.pipeline.result = result

t = threading.Thread(target=run_pipeline, daemon=True)
t.start()
dash.run()
"
fi
