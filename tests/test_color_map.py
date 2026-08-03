from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.visualization.color_map import build_color_map


class ColorMapTests(unittest.TestCase):
    def test_builds_interactive_joined_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = root / "variants.csv"
            colors = root / "colors.csv"
            output = root / "color-map.html"
            self._write_variants(variants)
            self._write_colors(colors)

            result = build_color_map(
                variants,
                colors,
                output,
                include_plotlyjs="cdn",
            )

            document = result.read_text(encoding="utf-8")
            self.assertIn("2 digital swatches", document)
            self.assertIn("Rare Beauty", document)
            self.assertIn("Ulta blush color map", document)
            self.assertIn("plotly_click", document)
            self.assertIn('id="ulta-detail-content"', document)
            self.assertIn("cooler magenta", document)
            self.assertIn("warmer coral", document)

    def test_rejects_incomplete_sku_join(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = root / "variants.csv"
            colors = root / "colors.csv"
            self._write_variants(variants)
            self._write_colors(colors, only_one=True)

            with self.assertRaisesRegex(ValueError, "SKU join is incomplete"):
                build_color_map(variants, colors, root / "color-map.html")

    @staticmethod
    def _write_variants(path: Path) -> None:
        rows = [
            {
                "product_id": "pimprod1",
                "sku_id": sku_id,
                "brand": "Rare Beauty",
                "product_name": "Soft Pinch Liquid Blush",
                "variant_name": shade,
                "variant_url": f"https://www.ulta.com/p/test-pimprod1?sku={sku_id}",
                "swatch_image_url": f"https://media.ultainc.com/i/ulta/{sku_id}_sw",
                "variant_image_url": f"https://media.ultainc.com/i/ulta/{sku_id}",
                "effective_price": "25.00",
                "size_value": "0.25",
                "size_unit": "oz",
                "price_per_g_ml": "3.53",
            }
            for sku_id, shade in (("100", "Hope"), ("101", "Happy"))
        ]
        ColorMapTests._write(path, rows)

    @staticmethod
    def _write_colors(path: Path, *, only_one: bool = False) -> None:
        rows = [
            {
                "product_id": "pimprod1",
                "sku_id": "100",
                "hex_color": "#e88891",
                "lab_l": "67.14",
                "lab_a": "37.59",
                "lab_b": "11.20",
            },
            {
                "product_id": "pimprod1",
                "sku_id": "101",
                "hex_color": "#f27c84",
                "lab_l": "65.72",
                "lab_a": "45.91",
                "lab_b": "16.74",
            },
        ]
        ColorMapTests._write(path, rows[:1] if only_one else rows)

    @staticmethod
    def _write(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
