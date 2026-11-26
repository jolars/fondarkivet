"""Read PLUSfonder NAVs from the data behind its fund charts."""

import json
from datetime import datetime
from decimal import Decimal
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from ..quotes import Quote, make_quote

SOURCE = "https://www.plusfonder.se"
# The chart endpoint identifies each SEK share class by its fund page ID.
FUNDS = {
    "SE0010323634": ("Mikrobolag", "plus-mikrobolag", 244022),
    "SE0010323642": ("Småbolag", "plus-smabolag", 244301),
    "SE0014991535": ("Allabolag", "plus-allabolag-sverige", 278591),
    "SE0016798805": ("Fastigheter", "plus-fastigheter-sverige", 284759),
    "SE0016828792": ("Teknologi", "plus-teknologi-sverige", 284761),
}


def _fetch_quote(isin: str, name: str, slug: str, page_id: int) -> Quote:
    url = f"{SOURCE}/tools/GetCoursesChartData?pageId={page_id}"
    with urlopen(url, timeout=30) as response:
        points = json.load(response, parse_float=Decimal)
    if not points:
        raise ValueError(f"Missing PLUSfonder NAVs for {isin}")
    timestamp, nav = max(points, key=lambda point: point[0])
    day = datetime.fromtimestamp(timestamp / 1000, ZoneInfo("Europe/Stockholm")).date()
    return make_quote(
        isin, f"PLUS {name} Sverige Index", day, Decimal(nav), "SEK", f"{SOURCE}/{slug}"
    )


def fetch_quotes() -> dict[str, Quote]:
    return {isin: _fetch_quote(isin, *fund) for isin, fund in FUNDS.items()}
