# Ulta Analysis

This project collects public Ulta product, variant, price, image, and ingredient
data into reproducible raw snapshots.

## Install

Use Python 3.11 or newer:

```powershell
python -m pip install -e .
```

## Configuration

Configuration is deliberately split into two files:

- `configs/scraper.toml` contains shared request, retry, delay, and checkpoint
  behavior.
- `configs/collections.toml` contains only named Ulta listing or product URLs.

To add skincare, body care, hair care, or another makeup category, add one
table to `collections.toml`:

```toml
[collections.body_lotion]
source_url = "https://www.ulta.com/shop/body-care/body-moisturizers/body-lotion"
source_type = "listing"
```

No Python change and no duplicate settings file are needed.

## Run

First discover a collection without scraping product pages:

```powershell
python scripts/scrape_ulta.py --collection blush --discover-only
```

Then run a small sample:

```powershell
python scripts/scrape_ulta.py --collection blush --max-products 5
```

Run another configured collection by name:

```powershell
python scripts/scrape_ulta.py --collection shampoo --max-products 5
```

A one-off Ulta listing or product URL is also supported. Shared scraper settings
still come from `scraper.toml`:

```powershell
python scripts/scrape_ulta.py `
  --url "https://www.ulta.com/p/example-pimprod123?sku=1234567" `
  --name "example_product"
```

Use `--settings` or `--collections` only when those files live somewhere other
than their default paths. Resume an interrupted v2 run with:

```powershell
python scripts/scrape_ulta.py `
  --collection blush `
  --resume-run "data/raw/blush/20260723T120000Z"
```

## Raw-data format (schema v2)

Each execution creates:

```text
data/raw/{collection}/{run_id}/
  run_manifest.json
  collection_products.csv
  products.csv
  variants.csv
  ingredients.csv
  failures.csv
  checkpoint.json
```

The tables have separate responsibilities:

| File | Grain | Purpose |
| --- | --- | --- |
| `collection_products.csv` | one discovered product | Crawl inventory, listing page, and listing position |
| `products.csv` | one product | Product identity, URL, rating, and review count |
| `variants.csv` | one SKU | Shade/variant identity, prices, size, availability, images, and ingredient-set link |
| `ingredients.csv` | one distinct formula per product | The exact raw ingredient text |

`ingredient_set_id` is a SHA-256 identifier computed from the product ID and
Unicode-normalized ingredient text. If all shades use the same formula, that
long ingredient list is stored once. If Ulta publishes different formulas for
different SKUs, each variant points to the correct formula.

Fields intentionally not collected include `summary`, `details`, `how_to_use`,
`currency`, and repeated `source_page`/collection metadata. `variant_image_url`
is retained. Row-level `observed_at` is not used: the run's `started_at` and
`finished_at` live once in `run_manifest.json`.

`variant_without_ingredients_count` in the manifest makes missing ingredient
content visible instead of silently pretending it was collected.

## Encoding policy

Ulta names and ingredients may contain French, Italian, and other non-ASCII
text. The pipeline:

1. decodes response bytes strictly, preferring UTF-8;
2. never uses replacement characters to hide decoding failures;
3. normalizes parsed text to Unicode NFC;
4. writes CSV as UTF-8 with BOM (`utf-8-sig`) for reliable Excel import; and
5. writes JSON as UTF-8 with characters preserved rather than escaped.

Raw text is not transliterated and accents are not removed. Tests include
`Lancôme`, `Crème`, `Città`, and `Peut Contenir` round trips.

## Responsible collection

The client is single-threaded, rate-limited, and retry-bounded. It does not
attempt to bypass blocks, authentication, or access controls. Review Ulta's
current terms and crawl guidance before large or scheduled runs.

## Tests

Tests use saved HTML and do not contact Ulta:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests scripts
```
