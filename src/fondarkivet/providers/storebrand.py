"""Read Storebrand NAVs from the fund detail pages."""

from ..quotes import Quote
from .fondlista import fetch_quote

FUNDS = ("SE0004807097",)


def fetch_quotes() -> dict[str, Quote]:
    return {
        isin: fetch_quote(isin, f"https://storebrand.fondlista.se/details/{isin}/1")
        for isin in FUNDS
    }
