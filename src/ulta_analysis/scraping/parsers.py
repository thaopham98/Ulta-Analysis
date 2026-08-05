"""Pure HTML parsers for Ulta category and product pages."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from ulta_analysis.schemas import (
    IngredientRecord,
    ParsedProduct,
    ProductRecord,
    VariantRecord,
)


ULTA_ORIGIN = "https://www.ulta.com"
PRODUCT_TOKEN_PATTERN = re.compile(
    r"(pimprod\d+|xlsimpprod\d+|prod\d+|mkt\d+|vp\d+)",
    flags=re.IGNORECASE,
)
MONEY_PATTERN = r"\$?\s*(\d+(?:\.\d{1,2})?)"


class ParseError(ValueError):
    """Raised when a page does not satisfy the raw scrape contract."""


def normalize_ulta_url(url: str, base_url: str = ULTA_ORIGIN) -> str:
    parsed = urlparse(urljoin(base_url, url))
    if parsed.hostname not in {"ulta.com", "www.ulta.com"}:
        raise ValueError(f"Not an Ulta URL: {url}")
    query = parse_qs(parsed.query)
    kept_query = {}
    if query.get("sku"):
        kept_query["sku"] = query["sku"][0]
    return urlunparse(
        ("https", "www.ulta.com", parsed.path, "", urlencode(kept_query), "")
    )


def product_id_from_url(url: str) -> str | None:
    match = PRODUCT_TOKEN_PATTERN.search(urlparse(url).path)
    return match.group(1) if match else None


def sku_id_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("sku")
    return values[0] if values else None


def product_url_without_sku(url: str) -> str:
    parsed = urlparse(normalize_ulta_url(url))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def parse_category_page(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select(
        ".ProductCard a.pal-c-Link--absolute[href*='/p/'], "
        ".ProductListingResults__productCard a[href*='/p/']"
    )
    if not anchors:
        anchors = soup.select("a[href*='/p/']")

    products: dict[str, str] = {}
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        try:
            normalized = normalize_ulta_url(href, page_url)
        except ValueError:
            continue
        product_id = product_id_from_url(normalized)
        if product_id:
            products.setdefault(product_id.lower(), normalized)
    return list(products.values())


def parse_load_more_url(html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        text = anchor.get_text(" ", strip=True).lower()
        href = anchor.get("href", "")
        if "load more" in text and "page=" in href:
            return urljoin(page_url, href)
    return None

def _apollo_state(html: str):
    """Decode Ulta's embedded Apollo state once."""
    marker = "window.__APOLLO_STATE__"
    marker_start = html.find(marker)
    if marker_start == -1:
        return None

    json_start = html.find("{", marker_start + len(marker))
    if json_start == -1:
        return None

    try:
        state, _ = json.JSONDecoder().raw_decode(html[json_start:])
    except json.JSONDecodeError:
        return None

    return state


def _ingredients_from_apollo_state(state) -> str | None:
    if state is None:
        return None

    for value in _find_ingredient_strings(state):
        ingredients = _optional_text(value)
        if ingredients:
            return ingredients.replace(r"\[", "[").replace(r"\]", "]")

    return None


def _find_ingredient_strings(value):
    if isinstance(value, dict):
        ingredients = value.get("ingredients")
        if isinstance(ingredients, str):
            yield ingredients

        for key, child in value.items():
            if key != "ingredients":
                yield from _find_ingredient_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_ingredient_strings(child)


def _size_from_apollo_state(state, sku_id: str) -> str | None:
    """Find the product size, preferring the component for the requested SKU."""
    if state is None:
        return None

    fallback_sizes: list[str] = []

    for entry in _find_dimension_entries(state):
        label = _optional_text(entry.get("dimensionsLabel"))
        size = _optional_text(entry.get("dimensionsValue"))

        if not label or label.casefold() != "size" or not size:
            continue

        variants = entry.get("variants")
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, dict):
                    continue

                variant_sku = str(
                    variant.get("skuId")
                    or variant.get("sku")
                    or ""
                )

                if variant_sku == sku_id and variant.get("selected") is True:
                    return size

        fallback_sizes.append(size)

    return fallback_sizes[0] if fallback_sizes else None


def _find_dimension_entries(value):
    if isinstance(value, dict):
        if "dimensionsLabel" in value and "dimensionsValue" in value:
            yield value

        for child in value.values():
            yield from _find_dimension_entries(child)

    elif isinstance(value, list):
        for child in value:
            yield from _find_dimension_entries(child)


def parse_product_page(
    html: str,
    source_url: str,
) -> ParsedProduct:
    soup = BeautifulSoup(html, "html.parser")
    apollo_state = _apollo_state(html)
    schema = _find_product_schema(soup)
    if schema is None:
        raise ParseError("Product JSON-LD was not found")

    offer = schema.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}

    product_id = str(
        schema.get("productID") or product_id_from_url(source_url) or ""
    ).strip()
    sku_id = str(schema.get("sku") or sku_id_from_url(source_url) or "").strip()
    if not product_id:
        raise ParseError("Product ID was not found")
    if not sku_id:
        raise ParseError("SKU ID was not found")

    brand = _brand_name(schema.get("brand"))
    variant_name = _optional_text(schema.get("color"))
    product_name = _product_name(schema, variant_name, soup, brand)
    variant_url = normalize_ulta_url(
        str(offer.get("url") or source_url),
        source_url,
    )
    if not sku_id_from_url(variant_url):
        parsed = urlparse(variant_url)
        variant_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                urlencode({"sku": sku_id}),
                "",
            )
        )

    pricing_text = _text(soup.select_one(".ProductPricing"))
    list_price, sale_price = _parse_prices(pricing_text, offer.get("price"))
    rating, review_count = _parse_rating(schema.get("aggregateRating"))
    variant_urls = _variant_urls(soup, source_url)
    if variant_url not in variant_urls:
        variant_urls.insert(0, variant_url)

    resolved_variant_name = variant_name or _variant_name_from_swatch(
        soup,
        product_name,
        sku_id,
        source_url,
    )
    variant_type = _variant_type(soup, bool(variant_name))
    swatch_image_url = _selected_swatch_image(soup, sku_id, source_url)
    if not swatch_image_url and variant_type == "color":
        swatch_image_url = (
            f"https://media.ultainc.com/i/ulta/{sku_id}_sw"
            f"?img404={sku_id}&w=400&fmt=auto"
        )

    ingredients = (
        _ingredients_from_apollo_state(apollo_state)
        or _ingredients(soup)
    )
    ingredient_set_id = (
        hashlib.sha256(
            f"{product_id}\0{ingredients}".encode("utf-8", errors="strict")
        ).hexdigest()
        if ingredients
        else None
    )
    product = ProductRecord(
        product_id=product_id,
        brand=brand,
        product_name=product_name,
        product_url=product_url_without_sku(variant_url),
        rating=rating,
        review_count=review_count,
    )
    variant = VariantRecord(
        product_id=product_id,
        sku_id=sku_id,
        variant_type=variant_type,
        variant_name=resolved_variant_name,
        variant_description=_text(soup.select_one(".SwatchDropDown__description")),
        variant_url=variant_url,
        list_price=list_price,
        sale_price=sale_price,
        size_text=( _size_from_apollo_state(apollo_state, sku_id) or _parse_size(soup) ),
        availability=_availability(offer.get("availability")),
        swatch_image_url=swatch_image_url,
        variant_image_url=_image_url(schema.get("image")),
        ingredient_set_id=ingredient_set_id,
    )
    ingredient = (
        IngredientRecord(
            product_id=product_id,
            ingredient_set_id=ingredient_set_id,
            ingredients=ingredients,
        )
        if ingredients and ingredient_set_id
        else None
    )
    return ParsedProduct(
        product=product,
        variant=variant,
        ingredient=ingredient,
        variant_urls=tuple(variant_urls),
    )


def _find_product_schema(soup: BeautifulSoup) -> dict | None:
    for script in soup.select("script[type='application/ld+json']"):
        try:
            value = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("@type") == "Product":
                return candidate
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    if isinstance(node, dict) and node.get("@type") == "Product":
                        return node
    return None


def _brand_name(value) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    return _optional_text(value)


def _image_url(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return _optional_text(value)


def _product_name(
    schema: dict,
    shade_name: str | None,
    soup: BeautifulSoup,
    brand: str | None,
) -> str | None:
    name = _optional_text(schema.get("name"))
    if name and shade_name:
        suffix = f" - {shade_name}"
        if name.casefold().endswith(suffix.casefold()):
            name = name[: -len(suffix)].strip()
    if name:
        return name

    heading = _text(soup.select_one(".ProductInformation h1, main h1"))
    if heading and brand and heading.casefold().startswith(brand.casefold()):
        heading = heading[len(brand) :].strip()
    return heading


def _parse_prices(pricing_text: str | None, offer_price) -> tuple[float | None, float | None]:
    text = pricing_text or ""
    sale_match = re.search(rf"sale\s+price\s*{MONEY_PATTERN}", text, re.IGNORECASE)
    regular_match = re.search(
        rf"(?:regularly|list\s+price|reg)\s*{MONEY_PATTERN}",
        text,
        re.IGNORECASE,
    )
    offer_value = _float_or_none(offer_price)
    if sale_match:
        sale_price = _float_or_none(sale_match.group(1))
        list_price = (
            _float_or_none(regular_match.group(1)) if regular_match else offer_value
        )
        return list_price, sale_price
    return offer_value, None


def _parse_rating(value) -> tuple[float | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    rating = _float_or_none(value.get("ratingValue"))
    review_value = value.get("reviewCount")
    try:
        reviews = int(str(review_value).replace(",", "")) if review_value is not None else None
    except ValueError:
        reviews = None
    return rating, reviews


def _parse_size(soup: BeautifulSoup) -> str | None:
    dimension = soup.select_one(".ProductDimension")
    if not dimension:
        return None
    text = dimension.get_text(" ", strip=True)
    match = re.search(r"\bSize:\s*(.+)$", text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _variant_urls(soup: BeautifulSoup, source_url: str) -> list[str]:
    anchors = soup.select(".ProductSwatches--content a[href*='sku=']")
    if not anchors:
        anchors = soup.select(".ProductSwatches a[href*='sku=']")
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        try:
            normalized = normalize_ulta_url(href, source_url)
        except ValueError:
            continue
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def _selected_swatch_image(
    soup: BeautifulSoup,
    sku_id: str,
    source_url: str,
) -> str | None:
    for anchor in soup.select(".ProductSwatches--content a[href*='sku=']"):
        href = anchor.get("href")
        if href and sku_id_from_url(urljoin(source_url, href)) == sku_id:
            image = anchor.select_one("img[src]")
            if image:
                return urljoin(source_url, image["src"])
    image = soup.select_one(f"img[src*='/{sku_id}_sw']")
    return urljoin(source_url, image["src"]) if image else None


def _variant_name_from_swatch(
    soup: BeautifulSoup,
    product_name: str | None,
    sku_id: str,
    source_url: str,
) -> str | None:
    selected = None
    for anchor in soup.select(".ProductSwatches a[href*='sku=']"):
        href = anchor.get("href")
        if href and sku_id_from_url(urljoin(source_url, href)) == sku_id:
            selected = anchor
            break
    image = selected.select_one("img") if selected else None
    value = _optional_text(image.get("alt")) if image else None
    if not value and selected:
        value = _optional_text(selected.get_text(" ", strip=True))
    if value and product_name and value.casefold().endswith(product_name.casefold()):
        value = value[: -len(product_name)].strip()
    return value


def _variant_type(soup: BeautifulSoup, has_schema_color: bool) -> str:
    if has_schema_color:
        return "color"
    selectors = (
        ".ProductSwatches__label",
        ".ProductSwatches--label",
        ".ProductSwatches label",
        "[class*='ProductSwatches'] legend",
    )
    for selector in selectors:
        label = _text(soup.select_one(selector))
        if not label:
            continue
        match = re.search(
            r"\b(color|shade|size|scent|fragrance|flavor)\b",
            label,
            flags=re.IGNORECASE,
        )
        if match:
            value = match.group(1).casefold()
            return "color" if value == "shade" else value
    return "default"


def _availability(value) -> str | None:
    text = _optional_text(value)
    return text.rsplit("/", 1)[-1] if text else None


def _text(element) -> str | None:
    return _optional_text(element.get_text(" ", strip=True)) if element else None


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value).strip())
    return text or None


def _ingredients(soup: BeautifulSoup) -> str | None:
    """Extract only the ingredient accordion's text, preserving Unicode."""
    selectors = (
        "[data-test='ingredients']",
        "[data-testid='ingredients']",
        ".ProductDetails__ingredients",
        ".ProductDetail__ingredients",
        ".ProductDetails__productIngredients",
    )
    for selector in selectors:
        container = soup.select_one(selector)
        text = _ingredient_container_text(container)
        if text:
            return text

    for heading in soup.find_all(["h2", "h3", "h4", "button"]):
        label = _optional_text(heading.get_text(" ", strip=True))
        if not label or label.casefold().rstrip(":") not in {
            "ingredient",
            "ingredients",
        }:
            continue

        section = heading.find_parent(["section", "details", "li"])
        text = _ingredient_container_text(section)
        if text:
            return text

        anchor = heading.parent if heading.parent else heading
        for sibling in anchor.next_siblings:
            if not getattr(sibling, "get_text", None):
                continue
            text = _optional_text(sibling.get_text(" ", strip=True))
            if text:
                return text
    return None


def _ingredient_container_text(container) -> str | None:
    if not container:
        return None
    text = _optional_text(container.get_text(" ", strip=True))
    if not text:
        return None
    text = re.sub(r"^\s*ingredients?\s*:?\s*", "", text, flags=re.IGNORECASE)
    return _optional_text(text)


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None
