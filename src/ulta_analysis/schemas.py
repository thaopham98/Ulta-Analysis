"""Stable raw-data contracts produced by the scraper."""

from __future__ import annotations

from dataclasses import asdict, dataclass


COLLECTION_PRODUCT_FIELDS = (
    "product_id",
    "product_url",
    "listing_page",
    "listing_position",
)

PRODUCT_FIELDS = (
    "product_id",
    "brand",
    "product_name",
    "product_url",
    "rating",
    "review_count",
)

VARIANT_FIELDS = (
    "product_id",
    "sku_id",
    "variant_type",
    "variant_name",
    "variant_description",
    "variant_url",
    "list_price",
    "sale_price",
    "size_text",
    "availability",
    "swatch_image_url",
    "variant_image_url",
    "ingredient_set_id",
)

INGREDIENT_FIELDS = (
    "product_id",
    "ingredient_set_id",
    "ingredients",
)

FAILURE_FIELDS = (
    "occurred_at",
    "stage",
    "product_id",
    "url",
    "error_type",
    "message",
)


@dataclass(frozen=True)
class ProductRecord:
    product_id: str
    brand: str | None
    product_name: str | None
    product_url: str
    rating: float | None
    review_count: int | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VariantRecord:
    product_id: str
    sku_id: str
    variant_type: str
    variant_name: str | None
    variant_description: str | None
    variant_url: str
    list_price: float | None
    sale_price: float | None
    size_text: str | None
    availability: str | None
    swatch_image_url: str | None
    variant_image_url: str | None
    ingredient_set_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IngredientRecord:
    product_id: str
    ingredient_set_id: str
    ingredients: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ParsedProduct:
    product: ProductRecord
    variant: VariantRecord
    ingredient: IngredientRecord | None
    variant_urls: tuple[str, ...]
