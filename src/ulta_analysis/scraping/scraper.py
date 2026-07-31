"""End-to-end orchestration for normalized Ulta raw snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ulta_analysis.config import ScrapeConfig
from ulta_analysis.schemas import (
    COLLECTION_PRODUCT_FIELDS,
    INGREDIENT_FIELDS,
    PRODUCT_FIELDS,
    VARIANT_FIELDS,
)

from .checkpoint import (
    read_csv_rows,
    read_json,
    save_run_state,
    write_csv_atomic,
    write_json_atomic,
)
from .client import UltaClient
from .parsers import (
    normalize_ulta_url,
    parse_category_page,
    parse_load_more_url,
    parse_product_page,
    product_id_from_url,
    sku_id_from_url,
)


RAW_SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_run_id(value: datetime | None = None) -> str:
    return (value or utc_now()).strftime("%Y%m%dT%H%M%SZ")


class UltaScraper:
    def __init__(
        self,
        config: ScrapeConfig,
        *,
        output_root: str | Path = "data/raw",
        client: UltaClient | None = None,
    ):
        self.config = config
        self.output_root = Path(output_root)
        self.client = client or UltaClient(config)
        self._owns_client = client is None

    def discover_products(self) -> list[dict]:
        if self.config.resolved_source_type == "product":
            url = normalize_ulta_url(self.config.source_url)
            return [
                {
                    "product_id": product_id_from_url(url),
                    "product_url": url,
                    "listing_page": None,
                    "listing_position": 1,
                }
            ]

        current_url: str | None = self.config.source_url
        seen_pages: set[str] = set()
        products: dict[str, dict] = {}
        overall_position = 0

        for page_number in range(1, self.config.max_pages + 1):
            if not current_url or current_url in seen_pages:
                break
            seen_pages.add(current_url)
            print(f"[listing page {page_number}] {current_url}")
            html = self.client.get_text(current_url)
            page_products = parse_category_page(html, current_url)
            before = len(products)
            for url in page_products:
                product_id = product_id_from_url(url)
                if not product_id or product_id.lower() in products:
                    continue
                overall_position += 1
                products[product_id.lower()] = {
                    "product_id": product_id,
                    "product_url": url,
                    "listing_page": current_url,
                    "listing_position": overall_position,
                }
            print(
                f"  found {len(page_products)} product cards; "
                f"{len(products) - before} new; {len(products)} total"
            )
            next_url = parse_load_more_url(html, current_url)
            if not next_url or len(products) == before:
                break
            current_url = next_url

        return list(products.values())

    def discover_product_urls(self) -> list[str]:
        """Convenience view retained for callers that only need URLs."""
        return [row["product_url"] for row in self.discover_products()]

    def run(
        self,
        *,
        max_products: int | None = None,
        discover_only: bool = False,
        product_urls: list[str] | None = None,
        resume_run: str | Path | None = None,
    ) -> Path:
        started_at = utc_now()
        if resume_run:
            run_dir = Path(resume_run)
            run_id = run_dir.name
            if not run_dir.exists():
                raise FileNotFoundError(f"Resume directory does not exist: {run_dir}")
        else:
            run_id = new_run_id(started_at)
            run_dir = self.output_root / self.config.name / run_id
            run_dir.mkdir(parents=True, exist_ok=False)

        manifest_path = run_dir / "run_manifest.json"
        manifest = read_json(manifest_path)
        if manifest:
            _validate_resume_manifest(manifest, self.config)
        else:
            manifest = {
                "run_id": run_id,
                "collection": self.config.name,
                "source_url": self.config.source_url,
                "source_type": self.config.resolved_source_type,
                "market": "US",
                "started_at": iso_z(started_at),
                "finished_at": None,
                "status": "running",
                "raw_schema_version": RAW_SCHEMA_VERSION,
                "encoding": {
                    "html": "strict decoding; UTF-8 preferred",
                    "unicode_normalization": "NFC",
                    "csv": "UTF-8-SIG",
                    "json": "UTF-8",
                },
                "scraper_settings": {
                    key: value
                    for key, value in self.config.to_dict().items()
                    if key
                    not in {"name", "source_url", "source_type", "resolved_source_type"}
                },
            }
            write_json_atomic(manifest_path, manifest)

        inventory_path = run_dir / "collection_products.csv"
        if product_urls:
            inventory = _inventory_from_urls(product_urls)
        elif inventory_path.exists():
            inventory = read_csv_rows(inventory_path)
        else:
            inventory = self.discover_products()

        if max_products is not None:
            inventory = inventory[:max_products]
        write_csv_atomic(inventory_path, inventory, COLLECTION_PRODUCT_FIELDS)
        urls = [row["product_url"] for row in inventory]

        if discover_only:
            save_run_state(
                run_dir,
                products=[],
                variants=[],
                ingredients=[],
                failures=[],
                completed_product_ids=set(),
                product_urls=urls,
                state="discovered",
            )
            manifest.update(
                {
                    "finished_at": iso_z(),
                    "status": "discovered",
                    "inventory_product_count": len(urls),
                    "product_count": 0,
                    "variant_count": 0,
                    "ingredient_set_count": 0,
                    "failure_attempt_count": 0,
                    "unresolved_product_count": len(urls),
                }
            )
            write_json_atomic(manifest_path, manifest)
            return run_dir

        products = read_csv_rows(run_dir / "products.csv")
        variants = read_csv_rows(run_dir / "variants.csv")
        ingredients = read_csv_rows(run_dir / "ingredients.csv")
        failures = read_csv_rows(run_dir / "failures.csv")
        checkpoint = read_json(run_dir / "checkpoint.json")
        completed = set(checkpoint.get("completed_product_ids", []))
        known_products = {str(row.get("product_id", "")) for row in products}
        known_skus = {str(row.get("sku_id", "")) for row in variants}
        known_ingredient_sets = {
            str(row.get("ingredient_set_id", "")) for row in ingredients
        }

        for index, product_url in enumerate(urls, start=1):
            product_id = product_id_from_url(product_url) or product_url
            if product_id in completed:
                continue
            print(f"[product {index}/{len(urls)}] {product_id}")
            product_failed = False
            try:
                initial_html = self.client.get_text(product_url)
                parsed = parse_product_page(initial_html, product_url)
                _append_parsed(
                    parsed,
                    products,
                    variants,
                    ingredients,
                    known_products,
                    known_skus,
                    known_ingredient_sets,
                )

                for variant_url in parsed.variant_urls:
                    variant_sku = sku_id_from_url(variant_url)
                    if variant_sku and variant_sku in known_skus:
                        continue
                    try:
                        variant_html = self.client.get_text(variant_url)
                        variant = parse_product_page(variant_html, variant_url)
                        _append_parsed(
                            variant,
                            products,
                            variants,
                            ingredients,
                            known_products,
                            known_skus,
                            known_ingredient_sets,
                        )
                    except Exception as error:
                        product_failed = True
                        failures.append(
                            _failure_row("variant", variant_url, product_id, error)
                        )
                        print(f"  variant failed: {variant_url}: {error}")

                if not product_failed:
                    completed.add(product_id)
            except Exception as error:
                failures.append(_failure_row("product", product_url, product_id, error))
                print(f"  product failed: {error}")

            if index % self.config.checkpoint_interval == 0:
                save_run_state(
                    run_dir,
                    products=products,
                    variants=variants,
                    ingredients=ingredients,
                    failures=failures,
                    completed_product_ids=completed,
                    product_urls=urls,
                    state="running",
                )

        state = "complete" if len(completed) == len(urls) else "partial"
        save_run_state(
            run_dir,
            products=products,
            variants=variants,
            ingredients=ingredients,
            failures=failures,
            completed_product_ids=completed,
            product_urls=urls,
            state=state,
        )
        manifest.update(
            {
                "finished_at": iso_z(),
                "status": state,
                "inventory_product_count": len(urls),
                "completed_product_count": len(completed),
                "product_count": len(products),
                "variant_count": len(variants),
                "ingredient_set_count": len(ingredients),
                "variant_without_ingredients_count": sum(
                    not row.get("ingredient_set_id") for row in variants
                ),
                "failure_attempt_count": len(failures),
                "unresolved_product_count": len(urls) - len(completed),
                "raw_fields": {
                    "collection_products.csv": list(COLLECTION_PRODUCT_FIELDS),
                    "products.csv": list(PRODUCT_FIELDS),
                    "variants.csv": list(VARIANT_FIELDS),
                    "ingredients.csv": list(INGREDIENT_FIELDS),
                },
            }
        )
        write_json_atomic(manifest_path, manifest)
        return run_dir

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "UltaScraper":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


def _append_parsed(
    parsed,
    products: list[dict],
    variants: list[dict],
    ingredients: list[dict],
    known_products: set[str],
    known_skus: set[str],
    known_ingredient_sets: set[str],
) -> None:
    product_id = parsed.product.product_id
    if product_id not in known_products:
        products.append(parsed.product.to_dict())
        known_products.add(product_id)
    sku_id = parsed.variant.sku_id
    if sku_id not in known_skus:
        variants.append(parsed.variant.to_dict())
        known_skus.add(sku_id)
    if (
        parsed.ingredient
        and parsed.ingredient.ingredient_set_id not in known_ingredient_sets
    ):
        ingredients.append(parsed.ingredient.to_dict())
        known_ingredient_sets.add(parsed.ingredient.ingredient_set_id)


def _inventory_from_urls(urls: list[str]) -> list[dict]:
    rows: list[dict] = []
    for position, url in enumerate(_dedupe_product_urls(urls), start=1):
        rows.append(
            {
                "product_id": product_id_from_url(url),
                "product_url": url,
                "listing_page": None,
                "listing_position": position,
            }
        )
    return rows


def _dedupe_product_urls(urls: list[str]) -> list[str]:
    products: dict[str, str] = {}
    for url in urls:
        normalized = normalize_ulta_url(url)
        key = (product_id_from_url(normalized) or normalized).lower()
        products.setdefault(key, normalized)
    return list(products.values())


def _failure_row(stage: str, url: str, product_id: str, error: Exception) -> dict:
    return {
        "occurred_at": iso_z(),
        "stage": stage,
        "product_id": product_id,
        "url": url,
        "error_type": type(error).__name__,
        "message": str(error)[:1000],
    }


def _validate_resume_manifest(manifest: dict, config: ScrapeConfig) -> None:
    if manifest.get("raw_schema_version") != RAW_SCHEMA_VERSION:
        raise ValueError(
            "Only raw schema v2 runs can be resumed; start a new run for old snapshots"
        )
    if manifest.get("collection") != config.name:
        raise ValueError("Resume run collection does not match the current config")
    if manifest.get("source_url") != config.source_url:
        raise ValueError("Resume run source URL does not match the current config")
