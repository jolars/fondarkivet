import json
import unittest
from io import BytesIO
from unittest.mock import patch

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
            name, quote = fondlista.fetch_quote(isin, url)

        self.assertEqual(name, "Storebrand FRN A")
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
        isin = "SE0000837338"
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
            _, quote = lansforsakringar._fetch_quote(isin)
            with self.assertRaises(ValueError):
                lansforsakringar._fetch_quote("SE0005188836")

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "5640.97")

    def test_swedbank_robur_uses_the_structured_nav_date(self):
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
            _, quote = swedbank_robur._fetch_quote("SE0000987224")

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "150.94")

    def test_plus_uses_the_latest_point_and_stockholm_date(self):
        # The newest point is 23:00 UTC on January 1, midnight in Stockholm.
        data = b"[[1767308400000,149.604870],[1767222000000,150.123456]]"
        isin = "SE0010323634"
        with patch.object(plus, "urlopen", return_value=BytesIO(data)):
            _, quote = plus._fetch_quote(isin, *plus.FUNDS[isin])

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "149.604870")

    def test_nordnet_checks_the_share_class_before_using_its_nav(self):
        isin = "SE0004544823"
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
            _, quote = nordnet._fetch_quote(isin, nordnet.FUNDS[isin])
            with self.assertRaises(ValueError):
                nordnet._fetch_quote("SE0002756973", nordnet.FUNDS[isin])

        self.assertEqual(quote["date"], "2026-01-02")
        self.assertEqual(quote["nav"], "165.99")
