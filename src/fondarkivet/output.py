"""Update the historical archive and build the static API files."""

import csv
import json
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile

from .quotes import Quote

FIELDS = ("isin", "date", "nav", "currency", "source_url")
WEB = Path(__file__).with_name("web")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(quotes: dict[str, Quote], archive: Path, site: Path) -> None:
    archive.mkdir(parents=True, exist_ok=True)
    metadata = archive / "funds.json"
    funds = (
        json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
    )
    funds.update(
        {
            isin: {"name": name, "source_url": quote["source_url"]}
            for isin, (name, quote) in quotes.items()
        }
    )
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=archive, delete_on_close=False
    ) as file:
        json.dump(funds, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        file.close()
        Path(file.name).replace(metadata)

    output = site / "v1" / "nav"
    output.mkdir(parents=True, exist_ok=True)
    latest = []
    catalog = []
    archived_isins = {path.stem for path in archive.glob("*.csv") if path.is_file()}
    for isin in sorted(archived_isins | quotes.keys()):
        path = archive / f"{isin}.csv"
        observations = {}
        if path.exists():
            with path.open(encoding="utf-8", newline="") as file:
                observations = {row["date"]: row for row in csv.DictReader(file)}
        current = quotes.get(isin)
        if current is not None:
            _, quote = current
            observations[quote["date"]] = quote
        if not observations:
            continue

        rows = [observations[day] for day in sorted(observations)]
        if current is not None:
            _write_csv(path, rows)
        _write_csv(output / path.name, rows)
        latest_row = rows[-1]
        latest.append(latest_row)
        fund = funds.get(isin, {"name": isin, "source_url": latest_row["source_url"]})
        catalog.append(
            {
                "isin": isin,
                "name": fund["name"],
                "currency": latest_row["currency"],
                "latest_date": latest_row["date"],
                "source_url": fund["source_url"],
            }
        )
    _write_csv(output / "latest.csv", latest)
    (output.parent / "funds.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name in (
        "index.html",
        "_headers",
        "logo.png",
        "favicon.svg",
        "favicon-96x96.png",
        "favicon.ico",
        "apple-touch-icon.png",
        "web-app-manifest-192x192.png",
        "web-app-manifest-512x512.png",
        "site.webmanifest",
    ):
        copyfile(WEB / name, site / name)
