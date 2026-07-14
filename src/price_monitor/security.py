from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse, urlunparse

PRIVATE_HOSTS = {"localhost", "localhost.localdomain"}
METADATA_IPS = {ipaddress.ip_address("169.254.169.254")}
ALLOWED_PORTS = {80, 443}
SECRET_PATTERNS = [
    re.compile(r"(postgres(?:ql)?://[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
    re.compile(r"([?&](?:password|token|secret|api[_-]?key)=)[^&\s]+", re.IGNORECASE),
]


@dataclass(frozen=True)
class UrlValidationResult:
    ok: bool
    normalized_url: str = ""
    error_code: str = ""
    error_message: str = ""


def normalize_public_url(url: str) -> UrlValidationResult:
    raw = (url or "").strip()
    if not raw:
        return _invalid("invalid_url", "URL vazia.")
    try:
        parsed = urlparse(raw)
    except ValueError:
        return _invalid("invalid_url", "URL invalida.")

    problem = _validate_parsed_url(parsed)
    if problem is not None:
        return problem

    host = parsed.hostname or ""
    host = host.strip(".").lower()
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=_normalized_netloc(parsed, host),
        fragment="",
    )

    resolution_problem = _validate_host_resolution(host)
    if resolution_problem is not None:
        return resolution_problem

    return UrlValidationResult(ok=True, normalized_url=urlunparse(normalized))


def validate_redirect_url(url: str) -> UrlValidationResult:
    return normalize_public_url(url)


def _validate_parsed_url(parsed: ParseResult) -> UrlValidationResult | None:
    if parsed.scheme.lower() not in {"http", "https"}:
        return _invalid("invalid_url", "Somente HTTP e HTTPS sao permitidos.")
    if not parsed.hostname:
        return _invalid("invalid_url", "Host ausente.")
    if parsed.username or parsed.password:
        return _invalid("invalid_url", "Credenciais embutidas na URL nao sao permitidas.")
    if parsed.port and parsed.port not in ALLOWED_PORTS:
        return _invalid("invalid_url", "Porta nao permitida.")
    host = parsed.hostname.strip(".").lower()
    if host in PRIVATE_HOSTS or host.endswith(".localhost"):
        return _invalid("invalid_url", "Hosts locais nao sao permitidos.")
    if _ip_is_blocked(host):
        return _invalid("invalid_url", "Endereco IP privado ou reservado nao permitido.")
    return None


def _normalized_netloc(parsed: ParseResult, host: str) -> str:
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if parsed.port:
        return f"{host_part}:{parsed.port}"
    return host_part


def _validate_host_resolution(host: str) -> UrlValidationResult | None:
    if _looks_like_ip(host):
        return None
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return _invalid("dns_error", "Nao foi possivel resolver o host.")
    for info in infos:
        ip = info[4][0]
        if _ip_is_blocked(ip):
            return _invalid("invalid_url", "O host resolve para endereco privado ou reservado.")
    return None


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _ip_is_blocked(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        return False
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip in METADATA_IPS
    )


def _invalid(code: str, message: str) -> UrlValidationResult:
    return UrlValidationResult(ok=False, error_code=code, error_message=message)


def sanitize_error_message(message: str, limit: int = 300) -> str:
    sanitized = message or ""
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(_redact_secret_match, sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > limit:
        return f"{sanitized[: limit - 3]}..."
    return sanitized


def _redact_secret_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 3:
        return f"{match.group(1)}***{match.group(3)}"
    return f"{match.group(1)}***"


def hash_password(password: str, iterations: int = 260_000) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    encoded_salt = base64.b64encode(salt).decode()
    encoded_digest = base64.b64encode(digest).decode()
    return f"pbkdf2_sha256${iterations}${encoded_salt}${encoded_digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_raw)
        expected = base64.b64decode(digest_raw)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(digest, expected)
