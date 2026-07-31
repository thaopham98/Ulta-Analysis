"""Command-line interface for Ulta scrape runs."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlparse

from ulta_analysis.config import (
    COLLECTION_NAME_PATTERN,
    load_collection,
    validate_config,
)
from ulta_analysis.scraping.parsers import product_id_from_url

from .scraper import UltaScraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect normalized Ulta products, variants, and ingredients."
    )
    parser.add_argument(
        "--settings",
        default="configs/scraper.toml",
        help="Shared scraper settings TOML.",
    )
    parser.add_argument(
        "--collections",
        default="configs/collections.toml",
        help="Named collection registry TOML.",
    )
    parser.add_argument(
        "--collection",
        default="blush",
        help="Collection key from collections.toml.",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Override the config source URL for a one-off listing or product run.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Output collection name used with --url (otherwise inferred).",
    )
    parser.add_argument(
        "--output-root",
        default="data/raw",
        help="Root directory for immutable raw scrape runs.",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=None,
        help="Limit product pages for a verification run.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Only collect the product URL inventory.",
    )
    parser.add_argument(
        "--product-url",
        action="append",
        default=None,
        help="Scrape a specific product URL; may be supplied more than once.",
    )
    parser.add_argument(
        "--resume-run",
        default=None,
        help="Existing data/raw/{collection}/{run_id} directory to resume.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_products is not None and args.max_products < 1:
        raise SystemExit("--max-products must be at least 1")
    if args.name and not args.url:
        raise SystemExit("--name can only be used with --url")

    try:
        config = load_collection(args.settings, args.collections, args.collection)
    except (OSError, TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    if args.url:
        name = args.name or _infer_collection_name(args.url)
        if not COLLECTION_NAME_PATTERN.fullmatch(name):
            raise SystemExit(
                "--name must contain only lowercase letters, numbers, hyphens, "
                "and underscores"
            )
        config = replace(
            config,
            name=name,
            source_url=args.url,
            source_type="auto",
        )
        try:
            validate_config(config)
        except ValueError as error:
            raise SystemExit(str(error)) from error

    with UltaScraper(config, output_root=Path(args.output_root)) as scraper:
        run_dir = scraper.run(
            max_products=args.max_products,
            discover_only=args.discover_only,
            product_urls=args.product_url,
            resume_run=args.resume_run,
        )

    print(f"Run outputs: {run_dir.resolve()}")
    return 0


def _infer_collection_name(url: str) -> str:
    product_id = product_id_from_url(url)
    if product_id:
        return product_id.lower()
    path_name = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].lower()
    name = re.sub(r"[^a-z0-9_-]+", "-", path_name).strip("-_")
    return name or "ulta-collection"


if __name__ == "__main__":
    raise SystemExit(main())
