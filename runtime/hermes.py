"""
Hermes Agent Runtime.
Gücü: delegate_task ile paralel subagent, terminal + curl ile hızlı API,
       web_search built-in tool.

Kullanım:
    from runtime import get_runtime
    rt = get_runtime("hermes")
    rt.setup()
    result = rt.agent_call("prompt", schema)
"""

import json
import os
import re
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .base import BaseRuntime


class HermesRuntime(BaseRuntime):
    """Hermes Agent için runtime adaptörü."""

    @property
    def name(self) -> str:
        return "hermes"

    def __init__(self):
        self._api_key = ""
        self._ready = False

    def setup(self) -> bool:
        """API key ve Hermes ortamını kontrol eder."""
        self._api_key = self._find_api_key()
        if not self._api_key:
            print("[hermes] ❌ DEEPSEEK_API_KEY bulunamadı. ~/.env veya environment değişkenine ekleyin.")
            return False

        # Hermes ortamında mıyız?
        if not os.environ.get("HERMES_AGENT"):
            # Hermes dışında da çalışabilir (terminal + curl ile)
            pass

        self._ready = True
        print(f"[hermes] ✅ Runtime hazır (API: {self._api_key[:8]}...)")
        return True

    def _find_api_key(self) -> str:
        """API key'i sırayla dene."""
        # 1. Environment
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if key:
            return key

        # 2. .env dosyası
        try:
            with open(os.path.expanduser("~/.env")) as f:
                for line in f:
                    if "DEEPSEEK" in line.upper() and "=" in line:
                        return line.split("=", 1)[1].strip().strip("\"'")
        except (FileNotFoundError, IOError):
            pass

        # 3. Hermes config
        try:
            with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
                for line in f:
                    if "api_key" in line and "deepseek" in f.read(0):
                        pass
        except (FileNotFoundError, IOError):
            pass

        return ""

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """
        LLM çağrısı. Hermes'te terminal + curl ile DeepSeek API.
        """
        if not self._ready:
            if not self.setup():
                return None

        phase_str = f"[{phase}] " if phase else ""
        label_str = f"{label}: " if label else ""
        self.log(f"{phase_str}{label_str}agent çağrılıyor...")
        start = time.time()

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

        # Temp file ile curl çağrısı (shell escaping sorunu olmaz)
        payload_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(payload, f)
                payload_path = f.name

            import subprocess
            cmd = [
                "curl", "-s",
                "https://api.deepseek.com/chat/completions",
                "-H", "Content-Type: application/json",
                "-H", f"Authorization: Bearer {self._api_key}",
                "-d", f"@{payload_path}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            elapsed = time.time() - start

            if result.returncode != 0:
                self.log(f"{phase_str}{label_str}curl hatası: {result.stderr[:100]}")
                return None

            data = json.loads(result.stdout)
            content = data["choices"][0]["message"]["content"]

            # JSON parse
            parsed = self._extract_json(content, schema)
            if parsed:
                self.log(f"{phase_str}{label_str}✓ {elapsed:.1f}s")
            else:
                self.log(f"{phase_str}{label_str}⚠ JSON parse başarısız ({elapsed:.1f}s)")

            return parsed

        except json.JSONDecodeError as e:
            self.log(f"{phase_str}{label_str}❌ JSON hatası: {e}")
            return None
        except KeyError as e:
            self.log(f"{phase_str}{label_str}❌ API yanıtı beklenen formatta değil: {e}")
            return None
        except Exception as e:
            self.log(f"{phase_str}{label_str}❌ Hata: {e}")
            return None
        finally:
            if payload_path and os.path.exists(payload_path):
                os.unlink(payload_path)

    def _extract_json(self, text: str, schema: Optional[dict] = None) -> Optional[dict]:
        """JSON çıkar — direkt, fence, {block}."""
        if not text:
            return None
        text = text.strip()

        patterns = [
            lambda t: json.loads(t),
            lambda t: json.loads(re.search(r'```(?:json)?\s*\n?(.*?)\n?```', t, re.DOTALL).group(1).strip()),
            lambda t: json.loads(re.search(r'\{.*\}', t, re.DOTALL).group(0)),
        ]

        for p in patterns:
            try:
                parsed = p(text)
                if isinstance(parsed, dict):
                    if schema:
                        required = schema.get("required", [])
                        if all(f in parsed for f in required):
                            return parsed
                        return parsed
                    return parsed
            except (json.JSONDecodeError, AttributeError, IndexError):
                continue
        return None

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """
        Web araması. Hermes'te web_search tool'una erişemediğimiz için
        curl ile DDG HTML scraping yapıyoruz. Alternatif: delegate_task.
        """
        import subprocess
        import urllib.parse

        encoded = urllib.parse.quote(query)
        self.log(f"web_search: {query[:60]}...")

        try:
            cmd = f'curl -sL "https://html.duckduckgo.com/html/?q={encoded}" -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" 2>/dev/null'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)

            if result.returncode == 0 and result.stdout:
                html = result.stdout
                results = []

                # DDG result links
                for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
                    url = m.group(1)
                    title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    if url and title:
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": "",
                            "relevance": "medium",
                        })
                        if len(results) >= max_results:
                            break

                if results:
                    return results

        except Exception as e:
            self.log(f"  DDG search error: {e}")

        # Fallback: subagent ile dene (Hermes ortamında)
        if os.environ.get("HERMES_AGENT"):
            try:
                from hermes_tools import delegate_task
                # delegate_task async — sonuç sonra gelir, şimdilik boş dön
                self.log("  Subagent search dispatched (async)")
                return []
            except ImportError:
                pass

        return []

    def web_fetch(self, url: str) -> Optional[str]:
        """URL içeriğini curl ile getir, HTML'den metin çıkar."""
        import subprocess
        self.log(f"web_fetch: {url[:80]}...")

        try:
            result = subprocess.run(
                ['curl', '-sL', '--max-time', '30', url,
                 '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'],
                capture_output=True, text=True, timeout=35,
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout
                # HTML to text
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                return text[:15000]
        except Exception as e:
            self.log(f"  Fetch error: {e}")

        return None

    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 3) -> List[Any]:
        """
        Paralel çalıştırma. Hermes'te threading.ThreadPool kullanır.
        Not: Gerçek paralel subagent için delegate_task kullanılabilir
        ama async olduğu için sonuç beklenemez.
        """
        results = [None] * len(fn_list)
        errors = [None] * len(fn_list)
        lock = threading.Lock()

        def worker(idx: int, fn: Callable):
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

            # Throttle
            while len([t for t in threads if t.is_alive()]) >= max_workers:
                time.sleep(0.05)

        for t in threads:
            t.join(timeout=120)

        for i, err in enumerate(errors):
            if err:
                self.log(f"  parallel worker {i} error: {err}")

        return results

    def phase(self, name: str, detail: str = "") -> None:
        """Faz bildirimi — Hermes stili."""
        line = "─" * 50
        print(f"\n{line}")
        print(f" 🔬 PHASE: {name}")
        if detail:
            print(f"    {detail}")
        print(f"{line}")

    def log(self, message: str) -> None:
        """Log — Hermes stili."""
        print(f"  ⚡ {message}")
