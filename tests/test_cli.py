from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.scraping.cli import main


class CliTests(unittest.TestCase):
    def test_one_off_product_url_is_inferred_without_network_access(self):
        source_url = (
            "https://www.ulta.com/p/curl-talk-clean-slate-daily-shampoo-"
            "pimprod2058990?sku=2659098"
        )
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "--settings",
                        str(PROJECT_ROOT / "configs" / "scraper.toml"),
                        "--collections",
                        str(PROJECT_ROOT / "configs" / "collections.toml"),
                        "--url",
                        source_url,
                        "--discover-only",
                        "--output-root",
                        directory,
                    ]
                )

            self.assertEqual(exit_code, 0)
            collection_dir = Path(directory) / "pimprod2058990"
            run_dirs = list(collection_dir.iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "collection_products.csv").exists())


if __name__ == "__main__":
    unittest.main()
