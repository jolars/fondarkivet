"""Update the historical archive and build the static API files."""

import csv
import json
from pathlib import Path

from .quotes import Quote

FIELDS = ("isin", "date", "nav", "currency", "source_url")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(quotes: dict[str, Quote], archive: Path, site: Path) -> None:
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
        _write_csv(path, rows)
        _write_csv(output / path.name, rows)
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
    _write_csv(output / "latest.csv", latest)
    (output.parent / "funds.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (site / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Fondarkivet</title>'
        '<h1>Fondarkivet</h1><ul><li><a href="v1/funds.json">Fund catalog</a></li>'
        '<li><a href="v1/nav/latest.csv">Latest NAVs</a></li></ul>\n',
        encoding="utf-8",
    )
