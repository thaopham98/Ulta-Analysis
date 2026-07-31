from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.config import collection_names, load_collection


SETTINGS = PROJECT_ROOT / "configs" / "scraper.toml"
COLLECTIONS = PROJECT_ROOT / "configs" / "collections.toml"


class ConfigTests(unittest.TestCase):
    def test_repository_collection_registry_is_valid(self):
        names = collection_names(COLLECTIONS)
        configs = [load_collection(SETTINGS, COLLECTIONS, name) for name in names]
        self.assertTrue(
            {
                "blush",
                "bronzer",
                "tinted_moisturizer",
                "face_moisturizer",
                "moisturizers",
                "shampoo",
                "curl_talk_shampoo",
                "bath_shower",
            }.issubset(names)
        )
        self.assertEqual(
            {config.resolved_source_type for config in configs},
            {"listing", "product"},
        )

    def test_blush_uses_shared_settings(self):
        config = load_collection(SETTINGS, COLLECTIONS, "blush")
        self.assertEqual(config.name, "blush")
        self.assertEqual(
            config.source_url,
            "https://www.ulta.com/shop/makeup/face/blush",
        )
        self.assertEqual(config.request_delay_seconds, 1.0)

    def test_non_ulta_url_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collections.toml"
            path.write_text(
                '[collections.blush]\nsource_url = "https://example.com/blush"\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_collection(SETTINGS, path, "blush")

    def test_unknown_collection_is_rejected(self):
        with self.assertRaises(ValueError):
            load_collection(SETTINGS, COLLECTIONS, "unknown")


if __name__ == "__main__":
    unittest.main()
