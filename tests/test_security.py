from __future__ import annotations

from price_monitor.security import normalize_public_url, validate_redirect_url


def test_accepts_public_https() -> None:
    result = normalize_public_url("https://example.com/product?x=1#fragment")
    assert result.ok
    assert result.normalized_url == "https://example.com/product?x=1"


def test_rejects_localhost() -> None:
    assert not normalize_public_url("http://localhost:8501").ok


def test_rejects_loopback_ipv4() -> None:
    assert not normalize_public_url("http://127.0.0.1/product").ok


def test_rejects_loopback_ipv6() -> None:
    assert not normalize_public_url("http://[::1]/product").ok


def test_rejects_private_ipv4() -> None:
    assert not normalize_public_url("http://192.168.1.20/product").ok


def test_rejects_metadata_endpoint() -> None:
    assert not normalize_public_url("http://169.254.169.254/latest/meta-data").ok


def test_rejects_embedded_credentials() -> None:
    assert not normalize_public_url("https://user:pass@example.com/product").ok


def test_rejects_unsupported_scheme() -> None:
    assert not normalize_public_url("file:///etc/passwd").ok


def test_rejects_unusual_port() -> None:
    assert not normalize_public_url("https://example.com:4443/product").ok


def test_redirect_to_private_address_is_rejected() -> None:
    assert not validate_redirect_url("http://10.0.0.1/internal").ok
