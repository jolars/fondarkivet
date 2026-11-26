"""Read Länsförsäkringar NAVs from the published fund facts."""

import re
from datetime import date
from urllib.request import urlopen

from bs4 import BeautifulSoup

from ..quotes import SWEDISH_PRICE, Quote, make_quote, swedish_decimal

FUNDS = (
    "SE0000837296",  # Japan Index
    "SE0000837338",  # Fastighetsfond A
    "SE0002656611",  # Sverige Index
    "SE0002793943",  # USA Index
    "SE0005188836",  # Global Index
    "SE0005796331",  # Tillväxtmarknad Index A
)


def _fetch_quote(isin: str) -> Quote:
    url = f"https://lf.fondlista.se/sv/1/details/{isin}"
    with urlopen(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    fields = {
        label.get_text(" ", strip=True): value.get_text(" ", strip=True)
        for label in soup.select("#FundFacts h3")
        if (value := label.find_next_sibling()) is not None
    }
    name = soup.select_one("h1")
    nav = fields.get("Kurs", "")
    if (
        fields.get("ISIN") != isin
        or name is None
        or not re.fullmatch(SWEDISH_PRICE, nav)
    ):
        raise ValueError(f"Invalid Länsförsäkringar fund facts for {isin}")
    return make_quote(
        isin,
        name.get_text(" ", strip=True),
        date.fromisoformat(fields["Datum"]),
        swedish_decimal(nav),
        fields["Basvaluta"],
        url,
    )


def fetch_quotes() -> dict[str, Quote]:
    return {isin: _fetch_quote(isin) for isin in FUNDS}
