from __future__ import annotations

import os

import httpx


def main() -> int:
    base_url = os.getenv("APP_BASE_URL")
    if not base_url:
        print("APP_BASE_URL is not set")
        return 2
    url = base_url.rstrip("/") + "/_stcore/health"
    response = httpx.get(url, timeout=15)
    print(f"{url} -> {response.status_code}")
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
