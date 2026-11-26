"""Validate and normalize fund quotes from providers."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

SWEDISH_PRICE = r"[0-9]+(?:\s+[0-9]{3})*(?:,[0-9]+)?"

type Quote = tuple[str, dict[str, str]]


def make_quote(
    isin: str, name: str, day: date, nav: Decimal, currency: str, source_url: str
) -> Quote:
    if (
        not name.strip()
        or not nav.is_finite()
        or nav <= 0
        or day > datetime.now(ZoneInfo("Europe/Stockholm")).date()
        or currency != "SEK"
    ):
        raise ValueError(f"Invalid fund name, NAV, date, or currency for {isin}")
    return name, {
        "isin": isin,
        "date": day.isoformat(),
        "nav": format(nav, "f"),
        "currency": currency,
        "source_url": source_url,
    }


def swedish_decimal(price: str) -> Decimal:
    return Decimal("".join(price.split()).replace(",", "."))
