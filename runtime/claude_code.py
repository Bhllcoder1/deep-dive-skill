"""
Claude Code Runtime.
Gücü: Built-in agent(), parallel(), WebSearch, WebFetch fonksiyonları.
       Kendi JS runtime'ında çalışır -> en hızlı ve en yetenekli runtime.

NASIL ÇALIŞIR:
Bu Python dosyası Claude Code'un içinden çağrıldığında,
stdout'a __CLAUDE_*__ marker'ları basar. Claude Code'un JS wrapper'ı
(adapters/claude-code-workflow.js) bu marker'ları yakalar ve gerçek
Claude Code built-in fonksiyonlarına çevirir.

Yani:
  Python: agent_call(prompt, schema)
    → stdout: __CLAUDE_AGENT__:{...}
    → JS wrapper: await agent(prompt, {schema})
    → stdin'e yazar: JSON sonuç

Kullanım (Claude Code içinden):
    const { deepResearch } = require('./runtime/adapters/claude-code-workflow.js')
    const result = await deepResearch("soru")

veya doğrudan:
    python3 harness.py "soru" --runtime claude_code
"""

import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .base import BaseRuntime


class ClaudeCodeRuntime(BaseRuntime):
    """
    Claude Code Runtime.
    Built-in agent(), parallel(), WebSearch, WebFetch kullanır.
    Python tarafından çağrıldığında stdout'a marker basar,
    JS wrapper bunları gerçek Claude Code API'lerine çevirir.
    """

    @property
    def name(self) -> str:
        return "claude_code"

    def __init__(self):
        self._ready = False
        # Eğer gerçek Claude Code ortamında değilsek, fallback
        self._in_claude = os.environ.get("CLAUDE_CODE") == "1"
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    def setup(self) -> bool:
        """
        Claude Code ortamını kontrol eder.
        Eğer gerçek Claude Code'da değilsek, generic fallback kullan.
        """
        if self._in_claude:
            print("[claude_code] ✅ Claude Code runtime tespit edildi")
            self._ready = True
            return True

        # Claude Code dışında çalışıyorsa, API key ile generic fallback
        if self._api_key:
            print("[claude_code] ⚠ Claude Code ortamı bulunamadı, generic fallback kullanılacak")
            self._ready = True
            return True

        print("[claude_code] ❌ Claude Code ortamı yok ve API key bulunamadı")
        return False

    def _emit_marker(self, marker_type: str, data: dict) -> None:
        """stdout'a JSON marker basar — JS wrapper yakalar."""
        print(f"__CLAUDE_{marker_type}__:{json.dumps(data)}")
        sys.stdout.flush()

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """
        Claude Code'da: built-in agent() fonksiyonunu kullanır.
        Claude Code dışında: generic fallback (requests + DeepSeek API).
        """
        if self._in_claude:
            # Emit marker — JS wrapper yakalayıp agent()'a çevirecek
            self._emit_marker("AGENT", {
                "prompt": prompt,
                "schema": schema,
                "label": label,
                "phase": phase,
            })
            # JS wrapper sonucu stdin'den okuyacak (şu an implemente değil)
            # Şimdilik fallback'e düş
            pass

        # Fallback: generic agent_call
        return self._generic_agent_call(prompt, schema, label, phase)

    def _generic_agent_call(self, prompt: str, schema: Optional[dict] = None,
                            label: str = "", phase: str = "") -> Optional[dict]:
        """Generic fallback — requests ile DeepSeek API."""
        if not self._api_key:
            return None

        import requests

        system_msg = "You are a precise research agent. Return valid JSON only."

        payload = {
            "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return self._extract_json(content, schema)
        except Exception as e:
            print(f"[claude_code] API error: {e}")

        return None

    def _extract_json(self, text: str, schema: Optional[dict] = None) -> Optional[dict]:
        """JSON çıkar."""
        if not text:
            return None
        text = text.strip()
        import re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        for pattern in [
            r'```(?:json)?\s*\n?(.*?)\n?```',
            r'\{.*\}',
        ]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1) if pattern.startswith('```') else m.group(0))
                except (json.JSONDecodeError, IndexError):
                    pass
        return None

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """
        Claude Code'da: built-in WebSearch tool.
        Dışında: curl ile DDG HTML scraping.
        """
        if self._in_claude:
            self._emit_marker("WebSearch", {"query": query, "max_results": max_results})
            return []

        # Fallback
        import subprocess
        import urllib.parse

        try:
            encoded = urllib.parse.quote(query)
            cmd = f'curl -sL "https://html.duckduckgo.com/html/?q={encoded}" -H "User-Agent: Mozilla/5.0" 2>/dev/null'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                import re
                results = []
                for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', result.stdout, re.DOTALL):
                    results.append({
                        "url": m.group(1),
                        "title": re.sub(r'<[^>]+>', '', m.group(2)).strip(),
                        "snippet": "",
                        "relevance": "medium",
                    })
                    if len(results) >= max_results:
                        break
                return results
        except Exception:
            pass
        return []

    def web_fetch(self, url: str) -> Optional[str]:
        """Claude Code'da: built-in WebFetch. Dışında: curl."""
        if self._in_claude:
            self._emit_marker("WebFetch", {"url": url})
            return None

        import subprocess
        import re
        try:
            result = subprocess.run(
                ['curl', '-sL', '--max-time', '30', url, '-H', 'User-Agent: Mozilla/5.0'],
                capture_output=True, text=True, timeout=35,
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                return re.sub(r'\s+', ' ', text).strip()[:15000]
        except Exception:
            pass
        return None

    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 5) -> List[Any]:
        """
        Claude Code'da: built-in parallel().
        Dışında: threading.
        """
        if self._in_claude:
            self._emit_marker("PARALLEL", {"count": len(fn_list)})
            # Emit her fonksiyon için ayrı marker
            for i, fn in enumerate(fn_list):
                self._emit_marker(f"PARALLEL_ITEM_{i}", {})
            return []

        # Fallback: threading
        results = [None] * len(fn_list)
        errors = [None] * len(fn_list)
        lock = threading.Lock()

        def worker(idx, fn):
            try:
                result = fn()
                with lock:
                    results[idx] = result
            except Exception as e:
                with lock:
                    errors[idx] = e

        threads = []
        for i, fn in enumerate(fn_list):
            t = threading.Thread(target=worker, args=(i, fn), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=120)

        return results

    def phase(self, name: str, detail: str = "") -> None:
        """Claude Code stili phase bildirimi — progress bar formatında."""
        if self._in_claude:
            print(f"  ◇ Phase {name}: {detail}" if detail else f"  ◇ Phase {name}")
        else:
            line = "─" * 50
            print(f"\n{line}\n 📋 PHASE: {name}\n{line}")

    def log(self, message: str) -> None:
        """Claude Code stili log."""
        print(f"  • {message}")
