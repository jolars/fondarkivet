"""Read Spiltan NAVs from the fund list."""

import re
from datetime import date
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..funds import Fund
from ..quotes import SWEDISH_PRICE, Quote, make_quote, swedish_decimal

SOURCE = "https://www.spiltanfonder.se"
LIST_URL = SOURCE + "/fonder"


def _parse_quotes(html: bytes, funds: list[Fund]) -> dict[str, Quote]:
    soup = BeautifulSoup(html, "html.parser")
    quotes = {}
    for fund in funds:
        isin = fund.isin
        path = f"/fonder/{fund.slug}"
        links = soup.select(f'expandable-content a[href="{path}"]')
        cards = {
            id(link.find_parent("expandable-content")): link.find_parent(
                "expandable-content"
            )
            for link in links
        }
        if len(cards) != 1:
            raise ValueError(f"Expected one fund card for {isin}, found {len(cards)}")
        card = next(iter(cards.values()))
        prices = [
            label.find_next_sibling("span")
            for label in card.select(".fund-table-cell-label")
            if label.get_text(strip=True) == "NAV-kurs"
        ]
        dates = card.select(".fund-table-cell-updated time[datetime]")
        if len(prices) != 1 or prices[0] is None or len(dates) != 1:
            raise ValueError(f"Missing or ambiguous price or date for {isin}")
        price = prices[0].get_text(" ", strip=True)
        match = re.fullmatch(rf"({SWEDISH_PRICE})\s+kr", price)
        if not match:
            raise ValueError(f"Invalid SEK price for {isin}: {price!r}")
        quotes[isin] = make_quote(
            isin,
            fund.name,
            date.fromisoformat(dates[0]["datetime"]),
            swedish_decimal(match[1]),
            "SEK",
            SOURCE + path,
        )
    return quotes


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    with urlopen(LIST_URL, timeout=30) as response:
        return _parse_quotes(response.read(), funds)
