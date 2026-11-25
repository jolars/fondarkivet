"""Collect fund managers' latest published NAVs and build the static API."""

import csv
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SOURCE = "https://www.spiltanfonder.se"
LIST_URL = SOURCE + "/fonder"
SPILTAN_FUNDS = {
    "SE0004297927": "spiltan-aktiefond-investmentbolag",
    "SE0008613939": "spiltan-globalfond-investmentbolag",
    "SE0005798329": "spiltan-hograntefond",
    "SE0002152140": "spiltan-rantefond-sverige",
}
AMF_FUNDS = ("SE0001184961", "SE0000739187", "SE0001185000")
HANDELSBANKEN_SOURCE = "https://handelsbanken.fondlista.se"
# The issuer's quick view uses a security ID. Its response confirms the ISIN.
HANDELSBANKEN_FUNDS = {
    "SE0000624421": ("F0GBR04F5Z", "Europa Index Criteria"),
    "SE0010127894": ("F00000ZFRG", "Norden Index Criteria"),
    "SE0015382114": ("F000016JFT", "Global Momentum"),
    "SE0013460920": ("F000014X0D", "Global Högutdelande Criteria"),
    "SE0010323675": ("F00000ZQ99", "Global Småbolag Index Criteria"),
}
FIELDS = ("isin", "date", "nav", "currency", "source_url")
SWEDISH_PRICE = r"[0-9]+(?:\s+[0-9]{3})*(?:,[0-9]+)?"


def make_quote(isin, name, day, nav, currency, source_url):
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


def swedish_decimal(price):
    return Decimal("".join(price.split()).replace(",", "."))


def parse_quotes(html):
    soup = BeautifulSoup(html, "html.parser")
    quotes = {}
    for isin, slug in SPILTAN_FUNDS.items():
        path = f"/fonder/{slug}"
        links = soup.select(f'expandable-content a[href="{path}"]')
        cards = {
            id(link.find_parent("expandable-content")): link.find_parent(
                "expandable-content"
            )
            for link in links
        }
        if len(cards) != 1:
            raise ValueError(f"Expected one fund card for {isin}, found {len(cards)}")
        card = next(iter(cards.values()))
        prices = [
            label.find_next_sibling("span")
            for label in card.select(".fund-table-cell-label")
            if label.get_text(strip=True) == "NAV-kurs"
        ]
        dates = card.select(".fund-table-cell-updated time[datetime]")
        if len(prices) != 1 or prices[0] is None or len(dates) != 1:
            raise ValueError(f"Missing or ambiguous price or date for {isin}")
        price = prices[0].get_text(" ", strip=True)
        match = re.fullmatch(rf"({SWEDISH_PRICE})\s+kr", price)
        if not match:
            raise ValueError(f"Invalid SEK price for {isin}: {price!r}")
        name = card.select_one(".fund-table-name")
        if name is None:
            raise ValueError(f"Missing fund name for {isin}")
        quotes[isin] = make_quote(
            isin,
            name.get_text(" ", strip=True),
            date.fromisoformat(dates[0]["datetime"]),
            swedish_decimal(match[1]),
            "SEK",
            SOURCE + path,
        )
    return quotes


def fetch_amf(isin):
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


def fetch_handelsbanken(isin, security_id, name):
    url = (
        "https://shb-be.fondlista.se/api/universe/quick-view-details"
        f"?secId={security_id}&webId=2"
    )
    request = Request(
        url, headers={"X-Domain": HANDELSBANKEN_SOURCE, "Accept-Language": "sv"}
    )
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


def fetch_quotes():
    with urlopen(LIST_URL, timeout=30) as response:
        quotes = parse_quotes(response.read())
    for isin in AMF_FUNDS:
        quotes[isin] = fetch_amf(isin)
    for isin, (security_id, name) in HANDELSBANKEN_FUNDS.items():
        quotes[isin] = fetch_handelsbanken(isin, security_id, name)
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
    for isin in sorted(quotes):
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
        catalog.append(
            {
                "isin": isin,
                "name": name,
                "currency": rows[-1]["currency"],
                "latest_date": rows[-1]["date"],
                "source_url": quote["source_url"],
            }
        )
    write_csv(output / "latest.csv", latest)
    (output.parent / "funds.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (site / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Swedish fund NAVs</title>'
        '<h1>Swedish fund NAVs</h1><ul><li><a href="v1/funds.json">Fund catalog</a></li>'
        '<li><a href="v1/nav/latest.csv">Latest NAVs</a></li></ul>\n',
        encoding="utf-8",
    )


if __name__ == "__main__":
    build(fetch_quotes(), Path(sys.argv[1]), Path(sys.argv[2]))
