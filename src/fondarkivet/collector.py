"""Collect the latest NAVs from all configured providers."""

from collections.abc import Callable
from pathlib import Path

from .funds import Fund, LookupFields, load_funds
from .providers import (
    amf,
    handelsbanken,
    lansforsakringar,
    nordnet,
    plus,
    spiltan,
    storebrand,
    swedbank_robur,
)
from .quotes import Quote

REGISTRY = Path(__file__).with_name("fund_registry.json")
PROVIDERS: dict[str, tuple[Callable[[list[Fund]], dict[str, Quote]], LookupFields]] = {
    "amf": (amf.fetch_quotes, {}),
    "handelsbanken": (
        handelsbanken.fetch_quotes,
        {"security_id": str, "share_class": str},
    ),
    "lansforsakringar": (lansforsakringar.fetch_quotes, {}),
    "nordnet": (nordnet.fetch_quotes, {"slug": str}),
    "plus": (plus.fetch_quotes, {"slug": str, "page_id": int}),
    "spiltan": (spiltan.fetch_quotes, {"slug": str}),
    "storebrand": (storebrand.fetch_quotes, {}),
    "swedbank_robur": (swedbank_robur.fetch_quotes, {}),
}


def fetch_quotes() -> dict[str, Quote]:
    funds = load_funds(
        REGISTRY, {name: fields for name, (_, fields) in PROVIDERS.items()}
    )
    quotes = {}
    for provider, share_classes in funds.items():
        fetch_provider_quotes, _ = PROVIDERS[provider]
        quotes.update(fetch_provider_quotes(share_classes))
    return quotes
