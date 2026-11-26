"""Read NAVs from Nordnet's fund detail pages."""

import json
from datetime import date
from decimal import Decimal

from bs4 import BeautifulSoup

from ..funds import Fund
from ..quotes import Quote, make_quote
from .http import open_url


def _fetch_quote(fund: Fund) -> Quote:
    isin = fund.isin
    url = f"https://www.nordnet.se/fonder/lista/{fund.slug}"
    with open_url(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    for script in soup.select("script:not([src])"):
        _, marker, payload = (script.string or "").partition("window.__initialProps__=")
        if marker:
            break
    else:
        raise ValueError(f"Missing Nordnet fund details for {isin}")
    # The page assigns the fund details as a JSON-encoded string.
    encoded, _ = json.JSONDecoder().raw_decode(payload.lstrip())
    details = json.loads(encoded, parse_float=Decimal)["initialProps"][
        "orderBookBffData"
    ]
    instrument = details["instrument"]
    if instrument["isin"] != isin:
        raise ValueError(f"Unexpected Nordnet share class for {isin}")
    nav = details["navInfo"]["latestNav"]
    return make_quote(
        isin,
        fund.name,
        date.fromisoformat(nav["date"]),
        Decimal(nav["value"]),
        instrument["orderBook"]["currency"],
        url,
    )


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {fund.isin: _fetch_quote(fund) for fund in funds}
