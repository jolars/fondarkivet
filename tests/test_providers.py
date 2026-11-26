import json
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fondarkivet import collector
from fondarkivet.funds import Fund
from fondarkivet.providers import (
    fondlista,
    lansforsakringar,
    nordnet,
    plus,
    swedbank_robur,
)


class ProviderTest(unittest.TestCase):
    def test_fondlista_selects_the_requested_share_class(self):
        isin = "SE0004807097"
        fund = Fund(isin, "Storebrand FRN Företagsobligation A SEK H")
        url = f"https://storebrand.fondlista.se/details/{isin}/1"
        html = b"""
        <script id="__NEXT_DATA__">
        {"props":{"pageProps":{"details":{"morningstar":[
          {"Isin":"SE0006964656","LegalName":"Storebrand FRN B"},
          {"Isin":"SE0004807097","LegalName":"Storebrand FRN A",
           "LastPrice":{"Date":"2026-01-02T00:00:00","Value":136.3379,
                        "Currency":{"Id":"SEK"}}}
        ]}}}}
        </script>
        """
        with patch.object(fondlista, "urlopen", return_value=BytesIO(html)):
            name, quote = fondlista.fetch_quote(fund, url)

        self.assertEqual(name, fund.name)
        self.assertEqual(
            quote,
            {
                "isin": isin,
                "date": "2026-01-02",
                "nav": "136.3379",
                "currency": "SEK",
                "source_url": url,
            },
        )

    def test_lansforsakringar_reads_swedish_nav_from_fund_facts(self):
        fund = Fund("SE0000837338", "Länsförsäkringar Fastighetsfond A")
        html = """
        <h1>Länsförsäkringar Fastighetsfond A</h1>
        <section id="FundFacts">
          <div><h3>ISIN</h3><div>SE0000837338</div></div>
          <div><h3>Kurs</h3><div>5&nbsp;640,97</div></div>
          <div><h3>Basvaluta</h3><div>SEK</div></div>
          <div><h3>Datum</h3><div>2026-01-02</div></div>
        </section>
        """
        with patch.object(
            lansforsakringar,
            "urlopen",
            side_effect=lambda *a, **kw: BytesIO(html.encode()),
        ):
            _, quote = lansforsakringar._fetch_quote(fund)
            with self.assertRaises(ValueError):
                lansforsakringar._fetch_quote(replace(fund, isin="SE0005188836"))

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "5640.97")

    def test_swedbank_robur_uses_the_structured_nav_date(self):
        fund = Fund("SE0000987224", "Swedbank Robur Realränta A")
        html = b"""
        <script type="application/ld+json">{"@type":"Organization"}</script>
        <script type="application/ld+json">
          {"@type":"InvestmentFund","name":"Swedbank Robur Realranta A",
           "identifier":{"propertyID":"ISIN","value":"SE0000987224"},
           "price":150.94,"priceCurrency":"SEK","priceValidUntil":"2026-01-02T00:00:00",
           "dateCreated":"2002-11-25T00:00:00"}
        </script>
        """
        with patch.object(swedbank_robur, "urlopen", return_value=BytesIO(html)):
            _, quote = swedbank_robur._fetch_quote(fund)

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "150.94")

    def test_plus_uses_the_latest_point_and_stockholm_date(self):
        # The newest point is 23:00 UTC on January 1, midnight in Stockholm.
        data = b"[[1767308400000,149.604870],[1767222000000,150.123456]]"
        isin = "SE0000000001"
        entry = {
            "provider": "plus",
            "name": "Example PLUS fund",
            "slug": "example-fund",
            "page_id": 123,
        }
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "fund_registry.json"
            registry.write_text(json.dumps({isin: entry}), encoding="utf-8")
            with (
                patch.object(collector, "REGISTRY", registry),
                patch.object(plus, "urlopen", return_value=BytesIO(data)) as urlopen,
            ):
                quotes = collector.fetch_quotes()

        urlopen.assert_called_once_with(
            "https://www.plusfonder.se/tools/GetCoursesChartData?pageId=123", timeout=30
        )
        self.assertEqual(set(quotes), {isin})
        name, quote = quotes[isin]
        self.assertEqual(name, "Example PLUS fund")
        self.assertEqual(quote["source_url"], "https://www.plusfonder.se/example-fund")
        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "149.604870")

    def test_rejects_invalid_registry_before_fetching_quotes(self):
        fund = {"name": "Example fund", "provider": "plus", "slug": "example"}
        valid = f'"SE0000000001": {json.dumps(fund | {"page_id": 1})}'
        unknown = {"name": "Example fund", "provider": "other"}
        invalid_entries = {
            "Duplicate key": valid,
            "Unknown provider": f'"SE0000000002": {json.dumps(unknown)}',
            "missing 'page_id'": f'"SE0000000002": {json.dumps(fund)}',
        }
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "fund_registry.json"
            with (
                patch.object(collector, "REGISTRY", registry),
                patch.object(plus, "urlopen") as urlopen,
            ):
                for message, invalid in invalid_entries.items():
                    with self.subTest(message=message):
                        registry.write_text(f"{{{valid}, {invalid}}}", encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, message):
                            collector.fetch_quotes()
                urlopen.assert_not_called()

    def test_nordnet_checks_the_share_class_before_using_its_nav(self):
        isin = "SE0004544823"
        fund = Fund(
            isin,
            "IKC Avkastningsfond",
            slug="ikc-avkastningsfond-sek-43ad6174",
        )
        data = {
            "initialProps": {
                "orderBookBffData": {
                    "instrument": {
                        "isin": isin,
                        "name": "IKC Avkastningsfond",
                        "orderBook": {"currency": "SEK"},
                    },
                    "navInfo": {
                        "latestNav": {"date": "2026-01-02", "value": 165.99},
                        "previousNav": {"date": "2025-12-30", "value": 165.98},
                    },
                }
            }
        }
        encoded = json.dumps(json.dumps(data))
        html = f"<script>window.__initialProps__={encoded};window.other=1;</script>"
        with patch.object(
            nordnet, "urlopen", side_effect=lambda *a, **kw: BytesIO(html.encode())
        ):
            _, quote = nordnet._fetch_quote(fund)
            with self.assertRaises(ValueError):
                nordnet._fetch_quote(replace(fund, isin="SE0002756973"))

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "165.99")
