"""Collect the latest NAVs from all configured providers."""

from .providers import amf, handelsbanken, spiltan
from .quotes import Quote


def fetch_quotes() -> dict[str, Quote]:
    return spiltan.fetch_quotes() | amf.fetch_quotes() | handelsbanken.fetch_quotes()
