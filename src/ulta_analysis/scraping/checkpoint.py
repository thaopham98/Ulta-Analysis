"""Atomic run outputs and resume state."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ulta_analysis.schemas import (
    FAILURE_FIELDS,
    INGREDIENT_FIELDS,
    PRODUCT_FIELDS,
    VARIANT_FIELDS,
)


def write_csv_atomic(
    path: Path,
    rows: list[dict],
    fieldnames: tuple[str, ...] | list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_run_state(
    run_dir: Path,
    *,
    products: list[dict],
    variants: list[dict],
    ingredients: list[dict],
    failures: list[dict],
    completed_product_ids: set[str],
    product_urls: list[str],
    state: str,
) -> None:
    write_csv_atomic(run_dir / "products.csv", products, PRODUCT_FIELDS)
    write_csv_atomic(run_dir / "variants.csv", variants, VARIANT_FIELDS)
    write_csv_atomic(run_dir / "ingredients.csv", ingredients, INGREDIENT_FIELDS)
    write_csv_atomic(run_dir / "failures.csv", failures, FAILURE_FIELDS)
    write_json_atomic(
        run_dir / "checkpoint.json",
        {
            "state": state,
            "completed_product_ids": sorted(completed_product_ids),
            "product_count": len(products),
            "variant_count": len(variants),
            "ingredient_set_count": len(ingredients),
            "failure_attempt_count": len(failures),
            "unresolved_product_count": len(product_urls) - len(completed_product_ids),
            "product_url_count": len(product_urls),
        },
    )
