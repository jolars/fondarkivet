"""Collect Spiltan's published NAVs and build the static API."""
import csv
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen

from bs4 import BeautifulSoup

SOURCE = "https://www.spiltanfonder.se"
LIST_URL = SOURCE + "/fonder"
FUNDS = {
    "SE0004297927": "spiltan-aktiefond-investmentbolag",
    "SE0008613939": "spiltan-globalfond-investmentbolag",
    "SE0005798329": "spiltan-hograntefond",
    "SE0002152140": "spiltan-rantefond-sverige",
}
FIELDS = ("isin", "date", "nav", "currency", "source_url")


def parse_quotes(html):
    soup = BeautifulSoup(html, "html.parser")
    quotes = {}
    for isin, slug in FUNDS.items():
        path = f"/fonder/{slug}"
        links = soup.select(f'expandable-content a[href="{path}"]')
        cards = {id(link.find_parent("expandable-content")): link.find_parent("expandable-content")
                 for link in links}
        if len(cards) != 1:
            raise ValueError(f"Expected one fund card for {isin}, found {len(cards)}")
        card = next(iter(cards.values()))
        prices = [label.find_next_sibling("span") for label in card.select(".fund-table-cell-label")
                  if label.get_text(strip=True) == "NAV-kurs"]
        dates = card.select(".fund-table-cell-updated time[datetime]")
        if len(prices) != 1 or prices[0] is None or len(dates) != 1:
            raise ValueError(f"Missing or ambiguous price or date for {isin}")
        price = prices[0].get_text(" ", strip=True)
        match = re.fullmatch(r"([0-9]+(?:\s+[0-9]{3})*(?:,[0-9]+)?)\s+kr", price)
        if not match:
            raise ValueError(f"Invalid SEK price for {isin}: {price!r}")
        nav = Decimal("".join(match[1].split()).replace(",", "."))
        day = date.fromisoformat(dates[0]["datetime"])
        if nav <= 0 or day > date.today():
            raise ValueError(f"Invalid NAV or future quote date for {isin}")
        name = card.select_one(".fund-table-name")
        if name is None:
            raise ValueError(f"Missing fund name for {isin}")
        quotes[isin] = (name.get_text(" ", strip=True), {
            "isin": isin, "date": day.isoformat(), "nav": str(nav),
            "currency": "SEK", "source_url": SOURCE + path,
        })
    return quotes


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(quotes, archive, site):
    archive.mkdir(parents=True, exist_ok=True)
    output = site / "v1" / "nav"
    output.mkdir(parents=True, exist_ok=True)
    latest = []
    catalog = []
    for isin in sorted(FUNDS):
        path = archive / f"{isin}.csv"
        observations = {}
        if path.exists():
            with path.open(encoding="utf-8", newline="") as file:
                observations = {row["date"]: row for row in csv.DictReader(file)}
        name, quote = quotes[isin]
        observations[quote["date"]] = quote
        rows = [observations[day] for day in sorted(observations)]
        write_csv(path, rows)
        write_csv(output / path.name, rows)
        latest.append(rows[-1])
        catalog.append({"isin": isin, "name": name, "currency": rows[-1]["currency"],
                        "latest_date": rows[-1]["date"], "source_url": quote["source_url"]})
    write_csv(output / "latest.csv", latest)
    (output.parent / "funds.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (site / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Swedish fund NAVs</title>'
        '<h1>Swedish fund NAVs</h1><ul><li><a href="v1/funds.json">Fund catalog</a></li>'
        '<li><a href="v1/nav/latest.csv">Latest NAVs</a></li></ul>\n', encoding="utf-8"
    )


if __name__ == "__main__":
    with urlopen(LIST_URL, timeout=30) as response:
        quotes = parse_quotes(response.read())
    build(quotes, Path(sys.argv[1]), Path(sys.argv[2]))
