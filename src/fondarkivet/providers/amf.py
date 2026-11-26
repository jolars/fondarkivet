"""Read AMF NAVs from the fund detail pages."""

from ..quotes import Quote
from .fondlista import fetch_quote

FUNDS = ("SE0001184961", "SE0000739187", "SE0001185000")


def fetch_quotes() -> dict[str, Quote]:
    return {
        isin: fetch_quote(
            isin, f"https://amf.fondlista.se/details/{isin}/7?parentHost=www.amf.se"
        )
        for isin in FUNDS
    }
