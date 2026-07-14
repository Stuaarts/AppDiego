from __future__ import annotations

from price_monitor.scraping.adapters.example_store import ExampleStoreAdapter
from price_monitor.scraping.adapters.generic import GenericStoreAdapter
from price_monitor.scraping.base import StoreAdapter

ADAPTERS: dict[str, type[StoreAdapter]] = {
    "generic": GenericStoreAdapter,
    "example_store": ExampleStoreAdapter,
}


def get_adapter(adapter_key: str | None) -> StoreAdapter:
    adapter_cls = ADAPTERS.get(adapter_key or "generic", GenericStoreAdapter)
    return adapter_cls()
