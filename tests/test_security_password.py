from __future__ import annotations

from price_monitor.security import hash_password, verify_password


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("senha-segura")
    assert verify_password("senha-segura", password_hash)
    assert not verify_password("errada", password_hash)
