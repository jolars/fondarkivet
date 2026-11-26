"""Read AMF NAVs from the fund detail pages."""

from ..funds import Fund
from ..quotes import Quote
from .fondlista import fetch_quote


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {
        fund.isin: fetch_quote(
            fund,
            f"https://amf.fondlista.se/details/{fund.isin}/7?parentHost=www.amf.se",
        )
        for fund in funds
    }
