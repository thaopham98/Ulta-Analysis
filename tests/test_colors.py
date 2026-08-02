from __future__ import annotations

import csv
from io import BytesIO
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.colors.extraction import measure_swatch_bytes, srgb_to_lab
from ulta_analysis.colors.pipeline import run_color_extraction
from ulta_analysis.scraping.checkpoint import read_csv_rows


def png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ColorExtractionTests(unittest.TestCase):
    def test_solid_swatch_returns_rgb_hex_and_lab(self):
        content = png_bytes(Image.new("RGB", (80, 80), (255, 126, 180)))

        result = measure_swatch_bytes(content)

        self.assertEqual((result.rgb_r, result.rgb_g, result.rgb_b), (255, 126, 180))
        self.assertEqual(result.hex_color, "#ff7eb4")
        self.assertAlmostEqual(result.lab_l, 69.10, places=2)
        self.assertAlmostEqual(result.lab_a, 54.69, delta=0.02)
        self.assertAlmostEqual(result.lab_b, -5.27, delta=0.02)
        self.assertEqual(result.rgb_spread, 0.0)

    def test_center_foreground_ignores_white_background(self):
        image = Image.new("RGB", (100, 100), "white")
        ImageDraw.Draw(image).rectangle((40, 40, 59, 59), fill=(132, 46, 57))

        result = measure_swatch_bytes(png_bytes(image), crop_fraction=0.40)

        self.assertEqual((result.rgb_r, result.rgb_g, result.rgb_b), (132, 46, 57))

    def test_rgb_to_lab_reference_points(self):
        self.assertEqual(tuple(round(value, 2) for value in srgb_to_lab(0, 0, 0)), (0.0, 0.0, 0.0))
        white = srgb_to_lab(255, 255, 255)
        self.assertAlmostEqual(white[0], 100.0, places=2)
        self.assertAlmostEqual(white[1], 0.0, places=2)
        self.assertAlmostEqual(white[2], 0.0, places=2)

    def test_csv_pipeline_is_resumable_and_preserves_keys(self):
        image_by_url = {
            "https://media.ultainc.com/i/ulta/100_sw": png_bytes(
                Image.new("RGB", (80, 80), (20, 40, 60))
            ),
            "https://media.ultainc.com/i/ulta/101_sw": png_bytes(
                Image.new("RGB", (80, 80), (200, 100, 80))
            ),
        }
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return image_by_url[url]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "variants.csv"
            output_path = root / "swatch_colors.csv"
            with input_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("product_id", "sku_id", "swatch_image_url"),
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "product_id": "pimprod1",
                            "sku_id": "100",
                            "swatch_image_url": "https://media.ultainc.com/i/ulta/100_sw",
                        },
                        {
                            "product_id": "pimprod1",
                            "sku_id": "101",
                            "swatch_image_url": "https://media.ultainc.com/i/ulta/101_sw",
                        },
                    ]
                )

            first = run_color_extraction(
                input_path,
                output_path,
                request_delay_seconds=0,
                checkpoint_interval=1,
                fetch_bytes=fetch,
            )
            second = run_color_extraction(
                input_path,
                output_path,
                request_delay_seconds=0,
                fetch_bytes=fetch,
            )

            self.assertEqual(first["status"], "complete")
            self.assertEqual(second["status"], "complete")
            self.assertEqual(len(calls), 2)
            rows = read_csv_rows(output_path)
            self.assertEqual([row["sku_id"] for row in rows], ["100", "101"])
            self.assertEqual(rows[0]["hex_color"], "#14283c")


if __name__ == "__main__":
    unittest.main()
