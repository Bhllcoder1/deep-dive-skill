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
    # Soru kod olarak değil argv[1] olarak geçer (tırnak/enjeksiyon güvenli).
    # `python3 -` KULLANILMAZ: stdin dashboard'un klavye girişine ayrılmıştır.
    PANEL_CODE='
import sys
import threading
from core.dashboard import Dashboard
from harness import deep_research

question = sys.argv[1]
dash = Dashboard()
dash.subtitle = question[:60]
dash._last_question = question

def run_pipeline():
    result = deep_research(question, show_dashboard=False)
    dash.pipeline.result = result

t = threading.Thread(target=run_pipeline, daemon=True)
t.start()
dash.run()
'
    python3 -c "$PANEL_CODE" "$1"
fi
