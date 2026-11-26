"""Read Swedbank Robur NAVs from the structured fund details."""

import json
from datetime import datetime
from decimal import Decimal
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..funds import Fund
from ..quotes import Quote, make_quote


def _fetch_quote(fund: Fund) -> Quote:
    isin = fund.isin
    url = f"https://swedbankrobur.fondlista.se/sv/details/{isin}"
    with urlopen(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        details = json.loads(script.string, parse_float=Decimal)
        if details.get("@type") == "InvestmentFund":
            break
    else:
        raise ValueError(f"Missing Swedbank Robur fund details for {isin}")
    if (
        details["identifier"]["propertyID"] != "ISIN"
        or details["identifier"]["value"] != isin
    ):
        raise ValueError(f"Unexpected Swedbank Robur share class for {isin}")
    # Robur puts the NAV valuation date in the structured priceValidUntil field.
    return make_quote(
        isin,
        fund.name,
        datetime.fromisoformat(details["priceValidUntil"]).date(),
        Decimal(details["price"]),
        details["priceCurrency"],
        url,
    )


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {fund.isin: _fetch_quote(fund) for fund in funds}
