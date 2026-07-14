from __future__ import annotations

from urllib.parse import urlparse

from price_monitor.scraping.adapters.generic import GenericStoreAdapter


class ExampleStoreAdapter(GenericStoreAdapter):
    key = "example_store"

    def supports(self, url: str) -> bool:
        return urlparse(url).hostname in {"example.test", "www.example.test"}
