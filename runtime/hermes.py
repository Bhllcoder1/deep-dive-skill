"""
Hermes Agent Runtime.
Gücü: terminal + curl ile hızlı API ve web erişimi; parallel işleri için
Hermes ortamında da güvenli Python worker'ları kullanır.

Kullanım:
    from runtime import get_runtime
    rt = get_runtime("hermes")
    rt.setup()
    result = rt.agent_call("prompt", schema)
"""

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, List, Optional
from urllib.parse import parse_qs, urlsplit

from core.jsonparse import extract_json_object
from core.parallel import run_bounded
from core.safefetch import fetch_text_with_curl
from core.urlsafe import is_public_http_url

from .base import BaseRuntime


class HermesRuntime(BaseRuntime):
    """Hermes Agent için runtime adaptörü."""

    API_TIMEOUT_SECONDS = 60
    FETCH_TIMEOUT_SECONDS = 30
    PARALLEL_TIMEOUT_SECONDS = 120
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    @property
    def name(self) -> str:
        return "hermes"

    def __init__(self):
        self._api_key = ""
        self._ready = False

    def setup(self) -> bool:
        """API key ve curl kullanılabilirliğini kontrol eder."""
        self._ready = False
        self._api_key = self._find_api_key()
        if not self._api_key:
            print("[hermes] ❌ DEEPSEEK_API_KEY bulunamadı. ~/.env veya environment değişkenine ekleyin.")
            return False

        if not shutil.which("curl"):
            print("[hermes] ❌ curl bulunamadı. Hermes runtime curl gerektirir.")
            return False

        self._ready = True
        print("[hermes] ✅ Runtime hazır (API anahtarı yapılandırıldı)")
        return True

    def _find_api_key(self) -> str:
        """API key'i environment, ~/.env ve Hermes config'ten sırayla dene."""
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if key:
            return key

        try:
            with open(os.path.expanduser("~/.env"), encoding="utf-8") as env_file:
                for line in env_file:
                    match = re.match(r"\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(.*?)\s*$", line, re.IGNORECASE)
                    if match:
                        key = self._clean_api_key(match.group(1))
                        if key:
                            return key
        except (FileNotFoundError, OSError, UnicodeError):
            pass

        # The previous implementation read zero bytes from this file, so this
        # branch could never find a key. Support the common nested YAML shape:
        #   deepseek:\n    api_key: sk-...
        try:
            with open(os.path.expanduser("~/.hermes/config.yaml"), encoding="utf-8") as config_file:
                section_indent = None
                for raw_line in config_file:
                    stripped = raw_line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    indent = len(raw_line) - len(raw_line.lstrip())
                    if re.match(r"deepseek\s*:\s*(?:#.*)?$", stripped, re.IGNORECASE):
                        section_indent = indent
                        continue
                    if section_indent is not None and indent <= section_indent:
                        section_indent = None
                    if section_indent is not None:
                        match = re.match(r"api[_-]?key\s*:\s*(.*?)\s*$", stripped, re.IGNORECASE)
                        if match:
                            key = self._clean_api_key(match.group(1))
                            if key:
                                return key
        except (FileNotFoundError, OSError, UnicodeError):
            pass

        return ""

    @staticmethod
    def _clean_api_key(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1].strip()
        return value

    @staticmethod
    def _chat_endpoint() -> Optional[str]:
        base = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            return None
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def agent_call(self, prompt: str, schema: Optional[dict] = None,
                   label: str = "", phase: str = "") -> Optional[dict]:
        """LLM çağrısı — Hermes'te terminal + curl ile DeepSeek API."""
        if not isinstance(prompt, str) or not prompt.strip():
            self.log("agent çağrısı boş veya geçersiz prompt nedeniyle atlandı")
            return None
        if schema is not None and not isinstance(schema, dict):
            self.log("agent çağrısı geçersiz schema nedeniyle atlandı")
            return None
        if not self._ready and not self.setup():
            return None

        endpoint = self._chat_endpoint()
        if not endpoint:
            self.log("geçersiz LLM_API_BASE")
            return None

        phase_str = f"[{phase}] " if phase else ""
        label_str = f"{label}: " if label else ""
        self.log(f"{phase_str}{label_str}agent çağrılıyor...")
        start = time.monotonic()
        payload_path = None

        payload = {
            "model": os.environ.get("LLM_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "You are a precise research agent. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as payload_file:
                json.dump(payload, payload_file, ensure_ascii=False)
                payload_path = payload_file.name

            result = subprocess.run(
                [
                    "curl", "-sS", "-L", "--connect-timeout", "10",
                    "--max-time", str(self.API_TIMEOUT_SECONDS),
                    "--write-out", "\n%{http_code}", endpoint,
                    "-H", "Content-Type: application/json",
                    "-H", f"Authorization: Bearer {self._api_key}",
                    "-d", f"@{payload_path}",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self.API_TIMEOUT_SECONDS + 5,
            )
            elapsed = time.monotonic() - start
            if result.returncode != 0:
                self.log(f"{phase_str}{label_str}curl hatası: {self._short_error(result.stderr)}")
                return None

            body, separator, status = result.stdout.rpartition("\n")
            if not separator or not status.isdigit():
                self.log(f"{phase_str}{label_str}curl HTTP durumunu döndürmedi")
                return None
            if not 200 <= int(status) < 300:
                self.log(f"{phase_str}{label_str}API HTTP {status}: {self._api_error_message(body)}")
                return None

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.log(f"{phase_str}{label_str}API geçersiz JSON döndürdü")
                return None
            if not isinstance(data, dict):
                self.log(f"{phase_str}{label_str}API yanıtı nesne değil")
                return None
            if "error" in data:
                self.log(f"{phase_str}{label_str}API hatası: {self._api_error_message(body)}")
                return None

            choices = data.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                self.log(f"{phase_str}{label_str}API yanıtında choices yok")
                return None
            message = choices[0].get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                self.log(f"{phase_str}{label_str}API yanıtında metin içeriği yok")
                return None

            parsed = extract_json_object(content, schema)
            if parsed is not None:
                self.log(f"{phase_str}{label_str}✓ {elapsed:.1f}s")
            else:
                self.log(f"{phase_str}{label_str}⚠ JSON parse/schema başarısız ({elapsed:.1f}s)")
            return parsed
        except subprocess.TimeoutExpired:
            self.log(f"{phase_str}{label_str}curl zaman aşımına uğradı")
            return None
        except (OSError, TypeError, ValueError, UnicodeError) as error:
            self.log(f"{phase_str}{label_str}agent hatası: {self._short_error(str(error))}")
            return None
        finally:
            if payload_path:
                try:
                    os.unlink(payload_path)
                except FileNotFoundError:
                    pass
                except OSError as error:
                    self.log(f"geçici payload silinemedi: {self._short_error(str(error))}")

    @staticmethod
    def _short_error(value: str) -> str:
        return " ".join(str(value).split())[:200] or "bilinmeyen hata"

    def _api_error_message(self, body: str) -> str:
        try:
            error = json.loads(body).get("error", {})
            if isinstance(error, dict):
                return self._short_error(error.get("message", "API hata ayrıntısı yok"))
        except (json.JSONDecodeError, AttributeError):
            pass
        return self._short_error(body)

    @staticmethod
    def _valid_result_limit(max_results: int) -> Optional[int]:
        if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 1:
            return None
        return max_results

    def _ddg_result_url(self, url: str) -> Optional[str]:
        url = html.unescape(url).strip()
        if url.startswith("//"):
            url = f"https:{url}"
        parsed = urlsplit(url)
        if parsed.hostname and parsed.hostname.lower().endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            url = parse_qs(parsed.query).get("uddg", [""])[0]
        return url if is_public_http_url(url) else None

    def web_search(self, query: str, max_results: int = 6) -> List[dict]:
        """DuckDuckGo HTML ile senkron web araması yapar."""
        limit = self._valid_result_limit(max_results)
        if not isinstance(query, str) or not query.strip() or limit is None:
            self.log("web_search geçersiz query veya max_results nedeniyle atlandı")
            return []
        self.log(f"web_search: {query[:60]}...")

        try:
            result = subprocess.run(
                [
                    "curl", "-sS", "-L", "--connect-timeout", "5", "--max-time", "15",
                    "https://html.duckduckgo.com/html/", "--get", "--data-urlencode", f"q={query}",
                    "-H", f"User-Agent: {self.USER_AGENT}",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
            )
            if result.returncode != 0:
                self.log(f"DDG search hatası: {self._short_error(result.stderr)}")
                return []

            results = []
            seen_urls = set()
            for match in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', result.stdout, re.DOTALL):
                url = self._ddg_result_url(match.group(1))
                title = html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
                if not url or not title or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append({"url": url, "title": title, "snippet": "", "relevance": "medium"})
                if len(results) >= limit:
                    break
            return results
        except subprocess.TimeoutExpired:
            self.log("DDG search zaman aşımına uğradı")
        except OSError as error:
            self.log(f"DDG search hatası: {self._short_error(str(error))}")
        return []

    def web_fetch(self, url: str) -> Optional[str]:
        """Public HTTP(S) URL'yi (yönlendirmeler ve DNS dahil kontrollü) metne çevirir."""
        if not is_public_http_url(url):
            self.log("web_fetch geçersiz, yerel veya desteklenmeyen URL nedeniyle atlandı")
            return None
        self.log(f"web_fetch: {url[:80]}...")
        text = fetch_text_with_curl(url, "curl", user_agent=self.USER_AGENT,
                                    max_time=self.FETCH_TIMEOUT_SECONDS)
        if text is None:
            self.log("fetch başarısız (reddedildi, hata veya zaman aşımı)")
        return text

    def run_parallel(self, fn_list: List[Callable[[], Any]],
                     max_workers: int = 3) -> List[Any]:
        """İşleri sınırlı sayıda worker ile, sıra korunarak çalıştırır."""
        if not isinstance(fn_list, list):
            raise TypeError("fn_list must be a list of callables")
        if any(not callable(fn) for fn in fn_list):
            raise TypeError("fn_list must contain only callables")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        return run_bounded(
            fn_list, max_workers, timeout=self.PARALLEL_TIMEOUT_SECONDS,
            on_error=lambda index, exc: self.log(
                f"parallel worker {index} error: {self._short_error(str(exc))}"),
            on_timeout=lambda count: self.log(f"parallel timeout: {count} iş tamamlanmadı"),
        )

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
