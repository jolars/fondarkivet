"""Read Swedbank Robur NAVs from the structured fund details."""

import json
from datetime import datetime
from decimal import Decimal
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..quotes import Quote, make_quote

FUNDS = (
    "SE0000709123",  # Ny Teknik A
    "SE0000987224",  # Realränta A
    "SE0007074117",  # Access Asien A
)


def _fetch_quote(isin: str) -> Quote:
    url = f"https://swedbankrobur.fondlista.se/sv/details/{isin}"
    with urlopen(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        fund = json.loads(script.string, parse_float=Decimal)
        if fund.get("@type") == "InvestmentFund":
            break
    else:
        raise ValueError(f"Missing Swedbank Robur fund details for {isin}")
    if (
        fund["identifier"]["propertyID"] != "ISIN"
        or fund["identifier"]["value"] != isin
    ):
        raise ValueError(f"Unexpected Swedbank Robur share class for {isin}")
    # Robur puts the NAV valuation date in the structured priceValidUntil field.
    return make_quote(
        isin,
        fund["name"],
        datetime.fromisoformat(fund["priceValidUntil"]).date(),
        Decimal(fund["price"]),
        fund["priceCurrency"],
        url,
    )


def fetch_quotes() -> dict[str, Quote]:
    return {isin: _fetch_quote(isin) for isin in FUNDS}
