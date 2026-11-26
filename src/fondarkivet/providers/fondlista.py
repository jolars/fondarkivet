"""Read NAVs from Fondlista pages with Next.js fund details."""

import json
from datetime import datetime
from decimal import Decimal
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..funds import Fund
from ..quotes import Quote, make_quote


def fetch_quote(fund: Fund, url: str) -> Quote:
    isin = fund.isin
    with urlopen(url, timeout=30) as response:
        data = BeautifulSoup(response.read(), "html.parser").select_one(
            "#__NEXT_DATA__"
        )
    if data is None or not data.string:
        raise ValueError(f"Missing Fondlista fund details for {isin}")
    details = json.loads(data.string, parse_float=Decimal)["props"]["pageProps"][
        "details"
    ]
    matches = [entry for entry in details["morningstar"] if entry.get("Isin") == isin]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one Fondlista fund for {isin}, found {len(matches)}"
        )
    price = matches[0]["LastPrice"]
    return make_quote(
        isin,
        fund.name,
        datetime.fromisoformat(price["Date"]).date(),
        Decimal(price["Value"]),
        price["Currency"]["Id"],
        url,
    )
