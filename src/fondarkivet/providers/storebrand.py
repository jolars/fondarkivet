"""Read Storebrand NAVs from the fund detail pages."""

from ..funds import Fund
from ..quotes import Quote
from .fondlista import fetch_quote


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {
        fund.isin: fetch_quote(
            fund, f"https://storebrand.fondlista.se/details/{fund.isin}/1"
        )
        for fund in funds
    }
