"""Read Länsförsäkringar NAVs from the published fund facts."""

import re
from datetime import date

from bs4 import BeautifulSoup

from ..funds import Fund
from ..quotes import SWEDISH_PRICE, Quote, make_quote, swedish_decimal
from .http import open_url


def _fetch_quote(fund: Fund) -> Quote:
    isin = fund.isin
    url = f"https://lf.fondlista.se/sv/1/details/{isin}"
    with open_url(url, timeout=30) as response:
        soup = BeautifulSoup(response.read(), "html.parser")
    fields = {
        label.get_text(" ", strip=True): value.get_text(" ", strip=True)
        for label in soup.select("#FundFacts h3")
        if (value := label.find_next_sibling()) is not None
    }
    nav = fields.get("Kurs", "")
    if fields.get("ISIN") != isin or not re.fullmatch(SWEDISH_PRICE, nav):
        raise ValueError(f"Invalid Länsförsäkringar fund facts for {isin}")
    return make_quote(
        isin,
        fund.name,
        date.fromisoformat(fields["Datum"]),
        swedish_decimal(nav),
        fields["Basvaluta"],
        url,
    )


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {fund.isin: _fetch_quote(fund) for fund in funds}
