"""Read AMF NAVs from the fund detail pages."""

import json
from datetime import datetime
from decimal import Decimal
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..quotes import Quote, make_quote

FUNDS = ("SE0001184961", "SE0000739187", "SE0001185000")


def _fetch_quote(isin: str) -> Quote:
    url = f"https://amf.fondlista.se/details/{isin}/7?parentHost=www.amf.se"
    with urlopen(url, timeout=30) as response:
        data = BeautifulSoup(response.read(), "html.parser").select_one(
            "#__NEXT_DATA__"
        )
    if data is None or not data.string:
        raise ValueError(f"Missing AMF fund details for {isin}")
    details = json.loads(data.string, parse_float=Decimal)["props"]["pageProps"][
        "details"
    ]
    matches = [fund for fund in details["morningstar"] if fund.get("Isin") == isin]
    if len(matches) != 1:
        raise ValueError(f"Expected one AMF fund for {isin}, found {len(matches)}")
    fund = matches[0]
    price = fund["LastPrice"]
    return make_quote(
        isin,
        fund["LegalName"],
        datetime.fromisoformat(price["Date"]).date(),
        Decimal(price["Value"]),
        price["Currency"]["Id"],
        url,
    )


def fetch_quotes() -> dict[str, Quote]:
    return {isin: _fetch_quote(isin) for isin in FUNDS}
