"""Shared safe page fetching: HTML-to-text and a redirect-checked, IP-pinned curl fetch."""

import contextlib
import html
import os
import re
import subprocess
import tempfile
from typing import Any, Callable, Dict, Iterator, Optional
from urllib.parse import urljoin, urlsplit

from core.urlsafe import Resolver, normalize_public_url, resolve_public

USER_AGENT = "DeepDive/1.0 (+https://github.com/Bhllcoder1/deep-dive-skill)"
MAX_TEXT_CHARS = 15_000


@contextlib.contextmanager
def secret_header_file(headers: Dict[str, str]) -> Iterator[str]:
    """Write headers (e.g. ``Authorization``) to a 0600 temp file for ``curl -H @file``.

    Keeps credentials out of the process argument list, which any local user can read
    with ``ps``."""
    fd, path = tempfile.mkstemp(suffix=".hdr")  # mkstemp creates the file with mode 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for name, value in headers.items():
                handle.write(f"{name}: {value}\n")
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


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


def jina_reader_fetch(url: str, curl_path: str = "curl", *, runner: Callable[..., Any] = subprocess.run,
                      max_bytes: int = 2_000_000) -> Optional[str]:
    """Last-resort fetch through r.jina.ai (renders JS pages, returns markdown). Opt-in via
    DR_FETCH_JINA=1 because the target URL is sent to a third party. Only public URLs are sent."""
    from core.urlsafe import is_safe_to_connect, normalize_public_url
    safe = normalize_public_url(url)
    if not safe or not is_safe_to_connect(safe):
        return None
    try:
        proc = runner([curl_path, "--silent", "--fail", "--connect-timeout", "5", "--max-time", "30",
                       "--max-filesize", str(max_bytes), "--", "https://r.jina.ai/" + safe],
                      capture_output=True, text=True, errors="replace", timeout=35)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or "").strip() if proc.returncode == 0 else ""
    return text[:max_bytes] or None
