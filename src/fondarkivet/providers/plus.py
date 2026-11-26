"""Read PLUSfonder NAVs from the data behind its fund charts."""

import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..funds import Fund
from ..quotes import Quote, make_quote
from .http import open_url

SOURCE = "https://www.plusfonder.se"


def _fetch_quote(fund: Fund) -> Quote:
    # The chart endpoint identifies each SEK share class by its fund page ID.
    url = f"{SOURCE}/tools/GetCoursesChartData?pageId={fund.page_id}"
    with open_url(url, timeout=30) as response:
        points = json.load(response, parse_float=Decimal)
    if not points:
        raise ValueError(f"Missing PLUSfonder NAVs for {fund.isin}")
    timestamp, nav = max(points, key=lambda point: point[0])
    day = datetime.fromtimestamp(timestamp / 1000, ZoneInfo("Europe/Stockholm")).date()
    return make_quote(
        fund.isin, fund.name, day, Decimal(nav), "SEK", f"{SOURCE}/{fund.slug}"
    )


def fetch_quotes(funds: list[Fund]) -> dict[str, Quote]:
    return {fund.isin: _fetch_quote(fund) for fund in funds}
