"""
Generic Runtime.
Her yerde çalışır: Python 3 + requests veya curl yeterli.
Gücü: Sıfır bağımlılık, her ortamda çalışır.
Yavaş: Web araması için DDG scraping, threading ile paralel.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

from .base import BaseRuntime


class GenericRuntime(BaseRuntime):
    """
    Generic Python runtime.
    Çalışması için: Python 3 + requests veya curl.
    """

    @property
    def name(self) -> str:
        return "generic"

    def __init__(self):
        self._api_key = ""
        self._ready = False
        self._has_requests = False

    def setup(self) -> bool:
        """API key ve requests/curl kontrolü."""
        self._api_key = os.environ.get("DEEPSEEK_API_KEY", "")

        if not self._api_key:
            # .env'den dene
            try:
                with open(os.path.expanduser("~/.env")) as f:
                    for line in f:
                        if "DEEPSEEK" in line.upper() and "=" in line:
                            self._api_key = line.split("=", 1)[1].strip().strip("\"'")
                            break
            except (FileNotFoundError, IOError):
                pass

        if not self._api_key:
            print("[generic] ❌ DEEPSEEK_API_KEY bulunamadı.")
            print("  export DEEPSEEK_API_KEY='sk-...'")
            return False

        # requests var mı?
        try:
            import requests  # noqa: F401
            self._has_requests = True
        except ImportError:
            self._has_requests = False
            # curl var mı?
            try:
                subprocess.run(["curl", "--version"], capture_output=True, timeout=3)
            except Exception:
                print("[generic] ❌ Ne requests ne curl bulunamadı. pip install requests yapın.")
                return False

        self._ready = True
        print(f"[generic] ✅ Runtime hazır (API: {self._api_key[:8]}..., requests={'✅' if self._has_requests else '❌'})")
        return True

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """LLM çağrısı — requests veya curl ile DeepSeek API."""
        if not self._ready:
            if not self.setup():
                return None

        start = time.time()
        phase_s = f"[{phase}] " if phase else ""
        label_s = f"{label}: " if label else ""
        print(f"  {phase_s}{label_s}agent ({self._api_key[:8]}...)")

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

        result = None

        # requests
        if self._has_requests:
            result = self._requests_call(payload, schema)

        # curl fallback
        if result is None:
            result = self._curl_call(payload, schema)

        elapsed = time.time() - start
        if result:
            print(f"  {phase_s}{label_s}✓ {elapsed:.1f}s")
        else:
            print(f"  {phase_s}{label_s}❌ failed ({elapsed:.1f}s)")

        return result

    def _requests_call(self, payload: dict, schema: Optional[dict]) -> Optional[dict]:
        """requests ile API çağrısı."""
        import requests
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                return self._extract_json(data["choices"][0]["message"]["content"], schema)
            else:
                print(f"  [generic] API hata {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  [generic] requests error: {e}")
        return None

    def _curl_call(self, payload: dict, schema: Optional[dict]) -> Optional[dict]:
        """curl ile API çağrısı."""
        import tempfile
        payload_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(payload, f)
                payload_path = f.name

            result = subprocess.run(
                ["curl", "-s", "https://api.deepseek.com/chat/completions",
                 "-H", "Content-Type: application/json",
                 "-H", f"Authorization: Bearer {self._api_key}",
                 "-d", f"@{payload_path}"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return self._extract_json(data["choices"][0]["message"]["content"], schema)
        except Exception as e:
            print(f"  [generic] curl error: {e}")
        finally:
            if payload_path and os.path.exists(payload_path):
                os.unlink(payload_path)
        return None

    def _extract_json(self, text: str, schema: Optional[dict] = None) -> Optional[dict]:
        """JSON çıkar."""
        if not text:
            return None
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        for pat in [r'```(?:json)?\s*\n?(.*?)\n?```', r'\{.*\}']:
            m = re.search(pat, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1) if pat.startswith('```') else m.group(0))
                except (json.JSONDecodeError, IndexError):
                    pass
        return None

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """Web araması — DDG API veya HTML scraping."""
        results = []

        # DDG API
        if self._has_requests:
            try:
                import requests
                resp = requests.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json"},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("Abstract"):
                        results.append({
                            "url": data.get("AbstractURL", ""),
                            "title": data.get("Heading", query),
                            "snippet": data.get("Abstract", ""),
                            "relevance": "high",
                        })
                    for r in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(r, dict) and "FirstURL" in r:
                            results.append({
                                "url": r["FirstURL"],
                                "title": r.get("Text", ""),
                                "snippet": r.get("Text", ""),
                                "relevance": "medium",
                            })
                    if results:
                        return results[:max_results]
            except Exception:
                pass

        # DDG HTML scraping (curl)
        try:
            encoded = urllib.parse.quote(query)
            result = subprocess.run(
                f'curl -sL "https://html.duckduckgo.com/html/?q={encoded}" -H "User-Agent: Mozilla/5.0" 2>/dev/null',
                shell=True, capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', result.stdout, re.DOTALL):
                    results.append({
                        "url": m.group(1),
                        "title": re.sub(r'<[^>]+>', '', m.group(2)).strip(),
                        "snippet": "",
                        "relevance": "medium",
                    })
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

        return results[:max_results]

    def web_fetch(self, url: str) -> Optional[str]:
        """URL fetch — requests veya curl."""
        if self._has_requests:
            try:
                import requests
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                if resp.status_code == 200:
                    return self._html_to_text(resp.text)
            except Exception:
                pass

        # curl
        try:
            result = subprocess.run(
                ['curl', '-sL', '--max-time', '30', url, '-H', 'User-Agent: Mozilla/5.0'],
                capture_output=True, text=True, timeout=35,
            )
            if result.returncode == 0 and result.stdout.strip():
                return self._html_to_text(result.stdout)
        except Exception:
            pass
        return None

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()[:15000]

    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 3) -> List[Any]:
        """Python threading ile paralel çalıştırma."""
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
            if len([t for t in threads if t.is_alive()]) >= max_workers:
                time.sleep(0.05)

        for t in threads:
            t.join(timeout=120)
        return results

    def phase(self, name: str, detail: str = "") -> None:
        line = "─" * 50
        print(f"\n{line}")
        print(f" 📋 PHASE: {name}")
        if detail:
            print(f"    {detail}")
        print(f"{line}")

    def log(self, message: str) -> None:
        print(f"  • {message}")
