"""Single URL-safety module: what the pipeline is allowed to fetch.

``normalize_public_url`` is the lexical gate (scheme, credentials, localhost,
private/reserved/ambiguous-numeric hosts). ``host_resolves_public`` is the
DNS-level gate that closes the "public name -> private IP" hole; call it right
before connecting (and again on every redirect hop).
"""

import ipaddress
import re
import socket
from typing import Any, Callable, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")
# Hosts such as "2130706433", "0x7f.1" or "017700000001" are legal IPv4 spellings for
# curl/libc but are not parsed by ``ipaddress``; they must never be treated as names.
_NUMERIC_HOST = re.compile(r"^(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+))*$", re.IGNORECASE)


def is_public_ip(address: Any) -> bool:
    """True only for globally routable unicast addresses."""
    if isinstance(address, str):
        try:
            address = ipaddress.ip_address(address)
        except ValueError:
            return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return bool(address.is_global) and not any((
        address.is_private, address.is_loopback, address.is_link_local,
        address.is_multicast, address.is_reserved, address.is_unspecified,
    ))


def normalize_public_url(value: Any) -> Optional[str]:
    """Return a normalized http(s) URL, or None if it is unsafe or malformed."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_URL_LENGTH or any(char.isspace() for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password):
            return None
        host = parsed.hostname.rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return None
    if not host or host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        return None
    try:
        if not is_public_ip(ipaddress.ip_address(host)):
            return None
    except ValueError:
        if _NUMERIC_HOST.match(host):
            return None

    netloc = f"[{host}]" if ":" in host else host
    if port and port not in {80, 443}:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def is_public_http_url(value: Any) -> bool:
    return normalize_public_url(value) is not None


Resolver = Callable[..., Iterable[Tuple[Any, ...]]]


def resolve_public(host: str, resolver: Optional[Resolver] = None) -> Optional[List[str]]:
    """Resolve ``host``; return its addresses only if *every* one is public, else None.

    This is the DNS-rebinding guard. A name that fails to resolve is rejected.
    Callers that can pin the connection to the returned address (see
    ``core.safefetch``) get a race-free check; others get the narrower
    check-then-connect guarantee.
    """
    host = (host or "").rstrip(".")
    if not host:
        return None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return [str(literal)] if is_public_ip(literal) else None
    try:
        infos = (resolver or socket.getaddrinfo)(host, None, type=socket.SOCK_STREAM)
        addresses = [info[4][0] for info in infos]
    except (OSError, UnicodeError):
        return None
    if not addresses or not all(is_public_ip(address) for address in addresses):
        return None
    return addresses


def host_resolves_public(host: str, resolver: Optional[Resolver] = None) -> bool:
    return resolve_public(host, resolver) is not None


def is_safe_to_connect(url: Any, resolver: Optional[Resolver] = None) -> bool:
    """Lexical + DNS check for one URL (use for the initial URL and each redirect hop)."""
    normalized = normalize_public_url(url)
    return bool(normalized) and host_resolves_public(urlsplit(normalized).hostname or "", resolver)
