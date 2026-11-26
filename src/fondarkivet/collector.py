"""Collect the latest NAVs from all configured providers."""

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


def fetch_quotes() -> dict[str, Quote]:
    return (
        spiltan.fetch_quotes()
        | amf.fetch_quotes()
        | handelsbanken.fetch_quotes()
        | lansforsakringar.fetch_quotes()
        | swedbank_robur.fetch_quotes()
        | storebrand.fetch_quotes()
        | plus.fetch_quotes()
        | nordnet.fetch_quotes()
    )
