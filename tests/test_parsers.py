from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ulta_analysis.scraping.parsers import (
    normalize_ulta_url,
    parse_category_page,
    parse_load_more_url,
    parse_product_page,
    product_id_from_url,
)


FIXTURES = Path(__file__).parent / "fixtures"


class CategoryParserTests(unittest.TestCase):
    def test_extracts_unique_product_urls_and_next_page(self):
        html = (FIXTURES / "category_page.html").read_text(encoding="utf-8")
        page_url = "https://www.ulta.com/shop/makeup/face/blush"
        urls = parse_category_page(html, page_url)

        self.assertEqual(len(urls), 2)
        self.assertEqual(
            product_id_from_url(urls[0]).lower(),
            "pimprod2055883",
        )
        self.assertEqual(
            parse_load_more_url(html, page_url),
            "https://www.ulta.com/shop/makeup/face/blush?page=2",
        )

    def test_normalization_keeps_only_sku(self):
        value = normalize_ulta_url(
            "https://ulta.com/p/example-pimprod1?sku=22&cmpid=test#reviews"
        )
        self.assertEqual(
            value,
            "https://www.ulta.com/p/example-pimprod1?sku=22",
        )


class ProductParserTests(unittest.TestCase):
    def test_parses_regular_product_and_variants(self):
        html = (FIXTURES / "product_regular.html").read_text(encoding="utf-8")
        parsed = parse_product_page(
            html,
            "https://www.ulta.com/p/soft-pinch-liquid-blush-pimprod2055883?sku=2647882",
        )
        product = parsed.product
        variant = parsed.variant

        self.assertEqual(product.brand, "Rare Beauty")
        self.assertEqual(product.product_name, "Soft Pinch Liquid Blush")
        self.assertEqual(variant.variant_name, "Hope")
        self.assertEqual(variant.variant_description, "nude mauve (dewy)")
        self.assertEqual(product.product_id, "pimprod2055883")
        self.assertEqual(variant.sku_id, "2647882")
        self.assertEqual(variant.list_price, 25.0)
        self.assertIsNone(variant.sale_price)
        self.assertEqual(variant.size_text, "0.25 oz")
        self.assertEqual(variant.availability, "InStock")
        self.assertIn("Crème de Cacao", parsed.ingredient.ingredients)
        self.assertIn("Città", parsed.ingredient.ingredients)
        self.assertIn("Peut Contenir", parsed.ingredient.ingredients)
        self.assertEqual(variant.ingredient_set_id, parsed.ingredient.ingredient_set_id)
        self.assertEqual(len(parsed.variant_urls), 2)

    def test_parses_sale_and_regular_price(self):
        html = (FIXTURES / "product_sale.html").read_text(encoding="utf-8")
        parsed = parse_product_page(
            html,
            "https://www.ulta.com/p/camo-liquid-blush-pimprod2042954?sku=2617738",
        )
        product = parsed.product
        variant = parsed.variant

        self.assertEqual(variant.list_price, 8.0)
        self.assertEqual(variant.sale_price, 7.0)
        self.assertEqual(product.review_count, 8631)
        self.assertEqual(variant.size_text, "0.13 oz")


if __name__ == "__main__":
    unittest.main()
