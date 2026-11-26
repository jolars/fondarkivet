"""Read Handelsbanken NAVs from fund quick views."""

import json
import re
from datetime import date
from urllib.request import Request, urlopen

from ..quotes import SWEDISH_PRICE, Quote, make_quote, swedish_decimal

SOURCE = "https://handelsbanken.fondlista.se"
# The issuer's quick view uses a security ID. Its response confirms the ISIN.
FUNDS = {
    "SE0000624421": ("F0GBR04F5Z", "Europa Index Criteria"),
    "SE0010127894": ("F00000ZFRG", "Norden Index Criteria"),
    "SE0015382114": ("F000016JFT", "Global Momentum"),
    "SE0013460920": ("F000014X0D", "Global Högutdelande Criteria"),
    "SE0010323675": ("F00000ZQ99", "Global Småbolag Index Criteria"),
}


def _fetch_quote(isin: str, security_id: str, name: str) -> Quote:
    url = (
        "https://shb-be.fondlista.se/api/universe/quick-view-details"
        f"?secId={security_id}&webId=2"
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
        or fields.get("shareClass") != "A1 SEK"
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
        f"Handelsbanken {name} (A1 SEK)",
        date.fromisoformat(match[3]),
        swedish_decimal(match[1]),
        match[2],
        url,
    )


def fetch_quotes() -> dict[str, Quote]:
    return {
        isin: _fetch_quote(isin, security_id, name)
        for isin, (security_id, name) in FUNDS.items()
    }
