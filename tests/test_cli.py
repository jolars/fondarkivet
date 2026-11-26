import csv
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fondarkivet.cli import main
from fondarkivet.quotes import make_quote


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


class CollectorCliTest(unittest.TestCase):
    def test_replaces_existing_observation_and_keeps_newer_nav(self):
        isin = "SE0004297927"
        other_isin = "SE0001184961"
        source_url = "https://example.org/fund"
        quotes = {
            isin: make_quote(
                isin,
                "First fund",
                date(2025, 1, 2),
                Decimal("101.50"),
                "SEK",
                source_url,
            ),
            other_isin: make_quote(
                other_isin,
                "Second fund",
                date(2025, 1, 3),
                Decimal(202),
                "SEK",
                source_url,
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            site = Path(directory) / "site"
            archive.mkdir()
            history = archive / f"{isin}.csv"
            history.write_text(
                "isin,date,nav,currency,source_url\n"
                f"{isin},2025-01-03,105.00,SEK,{source_url}\n"
                f"{isin},2025-01-02,100.00,SEK,{source_url}\n",
                encoding="utf-8",
            )

            with patch("fondarkivet.cli.fetch_quotes", return_value=quotes):
                main([str(archive), str(site)])
                main([str(archive), str(site)])

            rows = read_csv(history)
            self.assertEqual(
                [(row["date"], row["nav"]) for row in rows],
                [("2025-01-02", "101.50"), ("2025-01-03", "105.00")],
            )
            self.assertEqual(read_csv(site / "v1" / "nav" / history.name), rows)
            self.assertEqual(
                read_csv(site / "v1" / "nav" / "latest.csv"),
                [quotes[other_isin][1], rows[-1]],
            )
            catalog = json.loads(
                (site / "v1" / "funds.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [(fund["isin"], fund["latest_date"]) for fund in catalog],
                [(other_isin, "2025-01-03"), (isin, "2025-01-03")],
            )

    def test_requires_both_directories_before_fetching(self):
        with (
            patch("fondarkivet.cli.fetch_quotes") as fetch,
            redirect_stderr(StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main(["archive"])
        self.assertEqual(error.exception.code, 2)
        fetch.assert_not_called()
