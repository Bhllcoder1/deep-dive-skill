"""Shared safe page fetching: HTML-to-text and a redirect-checked, IP-pinned curl fetch."""

import html
import re
import subprocess
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlsplit

from core.urlsafe import Resolver, normalize_public_url, resolve_public

USER_AGENT = "DeepDive/1.0 (+https://github.com/Bhllcoder1/deep-dive-skill)"
MAX_TEXT_CHARS = 15_000


def html_to_text(content: Any, limit: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(content, str):
        return ""
    text = re.sub(r"<(?:script|style|noscript)[^>]*>.*?</(?:script|style|noscript)>", " ",
                  content, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def fetch_text_with_curl(url: str, curl_path: str = "curl", *, user_agent: str = USER_AGENT,
                         connect_timeout: int = 10, max_time: int = 30,
                         max_bytes: int = 2_000_000, max_redirects: int = 4,
                         resolver: Optional[Resolver] = None,
                         runner: Callable[..., Any] = subprocess.run) -> Optional[str]:
    """Fetch a public page as text with curl, or return None.

    Every hop (the first URL and each redirect target) is lexically validated and
    DNS-resolved; curl is then pinned to the checked address with ``--resolve`` so a
    second, different DNS answer (rebinding) cannot redirect the connection to a
    private host. Redirects are followed manually for exactly this reason.
    """
    current = normalize_public_url(url)
    for _ in range(max_redirects + 1):
        if not current:
            return None
        parts = urlsplit(current)
        host = parts.hostname or ""
        addresses = resolve_public(host, resolver)
        if not addresses:
            return None
        port = parts.port or (443 if parts.scheme == "https" else 80)
        pin = next((a for a in addresses if ":" not in a), None) or f"[{addresses[0]}]"
        command = [
            curl_path, "-sS", "--proto", "=http,https", "--max-redirs", "0",
            "--connect-timeout", str(connect_timeout), "--max-time", str(max_time),
            "--max-filesize", str(max_bytes), "-A", user_agent,
            "--resolve", f"{host}:{port}:{pin}",
            "-w", "\n%{http_code}\t%{redirect_url}", "--", current,
        ]
        try:
            proc = runner(command, capture_output=True, text=True, errors="replace",
                          timeout=max_time + connect_timeout + 5)
        except (OSError, subprocess.SubprocessError):
            return None
        body, _, trailer = (proc.stdout or "").rpartition("\n")
        code, _, location = trailer.partition("\t")
        if not code.isdigit():
            return None
        status = int(code)
        if 300 <= status < 400 and location.strip():
            current = normalize_public_url(urljoin(current, location.strip()))
            continue
        if proc.returncode != 0 or not 200 <= status < 300:
            return None
        return html_to_text(body) or None
    return None
