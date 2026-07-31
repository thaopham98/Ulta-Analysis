from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.config import ScrapeConfig
from ulta_analysis.scraping.checkpoint import read_csv_rows, write_csv_atomic
from ulta_analysis.scraping.client import decode_html
from ulta_analysis.scraping.scraper import UltaScraper


FIXTURES = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self, html: str):
        self.html = html
        self.requested_urls: list[str] = []

    def get_text(self, url: str) -> str:
        self.requested_urls.append(url)
        return self.html


class ScraperTests(unittest.TestCase):
    def test_listing_source_discovers_inventory_metadata(self):
        html = (FIXTURES / "category_page.html").read_text(encoding="utf-8")
        config = ScrapeConfig(
            name="blush",
            source_url="https://www.ulta.com/shop/makeup/face/blush",
            source_type="listing",
        )
        scraper = UltaScraper(config, client=FakeClient(html))

        inventory = scraper.discover_products()

        self.assertEqual(len(inventory), 2)
        self.assertEqual(inventory[0]["listing_position"], 1)
        self.assertEqual(inventory[0]["listing_page"], config.source_url)

    def test_product_source_becomes_one_product_inventory(self):
        source_url = (
            "https://www.ulta.com/p/curl-talk-clean-slate-daily-shampoo-"
            "pimprod2058990?sku=2659098"
        )
        config = ScrapeConfig(
            name="curl_talk_shampoo",
            source_url=source_url,
            source_type="product",
        )
        client = FakeClient("")
        scraper = UltaScraper(config, client=client)

        inventory = scraper.discover_products()
        self.assertEqual(inventory[0]["product_url"], source_url)
        self.assertIsNone(inventory[0]["listing_page"])
        self.assertEqual(client.requested_urls, [])

    def test_run_writes_normalized_tables(self):
        html = (FIXTURES / "product_regular.html").read_text(encoding="utf-8")
        source_url = (
            "https://www.ulta.com/p/blush-"
            "pimprod2044741?sku=2621261"
        )
        config = ScrapeConfig(
            name="sample_product",
            source_url=source_url,
            source_type="product",
            checkpoint_interval=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            run_dir = UltaScraper(
                config,
                output_root=directory,
                client=FakeClient(html),
            ).run()

            products = read_csv_rows(run_dir / "products.csv")
            variants = read_csv_rows(run_dir / "variants.csv")
            ingredients = read_csv_rows(run_dir / "ingredients.csv")
            self.assertEqual(len(products), 1)
            self.assertEqual(len(variants), 1)
            self.assertEqual(len(ingredients), 1)
            self.assertIn("Crème", ingredients[0]["ingredients"])
            self.assertNotIn("currency", variants[0])
            self.assertNotIn("source_page", variants[0])
            self.assertNotIn("observed_at", variants[0])
            self.assertNotIn("summary", products[0])
            self.assertEqual(
                variants[0]["ingredient_set_id"],
                ingredients[0]["ingredient_set_id"],
            )

            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["raw_schema_version"], 2)
            self.assertEqual(manifest["encoding"]["unicode_normalization"], "NFC")

    def test_utf8_decoding_and_csv_round_trip_preserve_accents(self):
        text = "Lancôme — Crème, Città, Peut Contenir"
        decoded = decode_html(text.encode("utf-8"))
        self.assertEqual(decoded, text)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unicode.csv"
            write_csv_atomic(path, [{"ingredients": decoded}], ("ingredients",))
            with path.open(newline="", encoding="utf-8-sig") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["ingredients"], text)


if __name__ == "__main__":
    unittest.main()
