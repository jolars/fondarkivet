"""Read Handelsbanken NAVs from fund quick views."""

import json
import re
from datetime import date
from urllib.request import Request, urlopen

from ..funds import Fund
from ..quotes import SWEDISH_PRICE, Quote, make_quote, swedish_decimal

SOURCE = "https://handelsbanken.fondlista.se"


def _fetch_quote(fund: Fund) -> Quote:
    isin = fund.isin
    # The issuer's quick view uses a security ID. Its response confirms the ISIN.
    url = (
        "https://shb-be.fondlista.se/api/universe/quick-view-details"
        f"?secId={fund.security_id}&webId=2"
    )
    request = Request(url, headers={"X-Domain": SOURCE, "Accept-Language": "sv"})
    with urlopen(request, timeout=30) as response:
        sections = json.load(response)
    fields = {
        field["id"]: field["value"]
        for section in sections
        if section["id"] == "fund_information"
        for field in section["data"]
    }
    if (
        fields.get("isin") != isin
        or fields.get("fundCompany") != "Handelsbanken Fonder AB"
        or fields.get("shareClass") != fund.share_class
    ):
        raise ValueError(f"Unexpected Handelsbanken fund details for {isin}")
    match = re.fullmatch(
        rf"({SWEDISH_PRICE})\s+(SEK)\s+\((\d{{4}}-\d{{2}}-\d{{2}})\)",
        fields["navKurs"],
    )
    if not match:
        raise ValueError(f"Invalid Handelsbanken NAV for {isin}: {fields['navKurs']!r}")
    return make_quote(
        isin,
        fund.name,
        date.fromisoformat(match[3]),
        swedish_decimal(match[1]),
        match[2],
        url,
    )


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {fund.isin: _fetch_quote(fund) for fund in funds}
