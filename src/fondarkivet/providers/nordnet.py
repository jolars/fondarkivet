"""Read NAVs for Nordnet Sverige Index and IKC Avkastningsfond from Nordnet."""

import json
from datetime import date
from decimal import Decimal
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..quotes import Quote, make_quote

FUNDS = {
    "SE0002756973": "nordnet-sverige-index-sek-aa7a9014",
    "SE0004544823": "ikc-avkastningsfond-sek-43ad6174",
}


def _fetch_quote(isin: str, slug: str) -> Quote:
    url = f"https://www.nordnet.se/fonder/lista/{slug}"
    with urlopen(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    for script in soup.select("script:not([src])"):
        _, marker, payload = (script.string or "").partition("window.__initialProps__=")
        if marker:
            break
    else:
        raise ValueError(f"Missing Nordnet fund details for {isin}")
    # The page assigns the fund details as a JSON-encoded string.
    encoded, _ = json.JSONDecoder().raw_decode(payload.lstrip())
    fund = json.loads(encoded, parse_float=Decimal)["initialProps"]["orderBookBffData"]
    instrument = fund["instrument"]
    if instrument["isin"] != isin:
        raise ValueError(f"Unexpected Nordnet share class for {isin}")
    nav = fund["navInfo"]["latestNav"]
    return make_quote(
        isin,
        instrument["name"],
        date.fromisoformat(nav["date"]),
        Decimal(nav["value"]),
        instrument["orderBook"]["currency"],
        url,
    )


def fetch_quotes() -> dict[str, Quote]:
    return {isin: _fetch_quote(isin, slug) for isin, slug in FUNDS.items()}
