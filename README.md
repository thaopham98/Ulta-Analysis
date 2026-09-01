# Ulta Beauty Product Data & Cosmetic Swatch Color Analysis

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
- `url`: the URL of the product.
- `name`: the output collection/folder name, not the product's display name. It must be a lowercase slug such as "bath_shower" or "blush".

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
  --resume-run "data/01_raw/blush/20260723T120000Z"
```

## Raw-data format (schema v2)

Each execution creates:

```text
data/01_raw/{collection}/{run_id}/
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

## Cleaning

### Basic Cleaning 
- Removes known discontinued products and SKUs.
- Removes products when all their variants are out of stock.
- Normalizes whitespace and non-breaking spaces.
- Converts empty strings to missing values.
- Handles known invalid values in size_text.

The implementation script is in:
```
src/ulta_analysis/cleaning/basic_cleaning.py
```

CLI to run the pipeline, remember to replace the `<RUN_ID>`:

```powershell
python -m ulta_analysis.cleaning.cli `
  --products "data/01_raw/blush/<RUN_ID>/products.csv" `
  --variants "data/01_raw/blush/<RUN_ID>/variants.csv" `
  --size-reference "data/reference/size/ulta_cleaned_single_blush.csv" `
  --output-dir "data/02_temp/blush/<RUN_ID>" `
  --color-output-dir "data/03_color_analysis/blush/<RUN_ID>"
```

You can edit where to input and output the datasets by changing the input and output paths.

### Fill Missing Sizes

Some `size_text` values are missing or invalid. This stage attempts to fill
them using another SKU from the same product, a historical reference dataset,
`SIZE_MAP_METRIC`, and `SIZE_MAP_OZ`. Values that cannot be resolved remain
missing and are recorded in a separate size-audit CSV.

The historical reference dataset was moved from:

`data/02_processed/test/blushes/cleaned/cleaned_single_blush.csv`

to:

`data/reference/size/ulta_cleaned_single_blush.csv`

This stage is included in the complete cleaning pipeline command above.

For example:
```powershell
python -m ulta_analysis.cleaning.cli `
  --products "data/01_raw/blush/20260724T001508Z/products.csv" `
  --variants "data/01_raw/blush/20260724T001508Z/variants.csv" `
  --size-reference "data/reference/size/ulta_cleaned_single_blush.csv" `
  --output-dir "data/02_temp/blush/20260724T001508Z" `
  --color-output-dir "data/03_color_analysis/blush/20260724T001508Z"
  ```
### Classification

Classifying blushes into different classes based on historical data:
|Class | Product|
|--|--|
|0 |  No usable swatch image|
|1 | Mono-color |
|2 | Multiple colors in the same color family|
|3 | Palettes and sets containing varied colors|
|Missing | New product requiring classification |

```powershell
python -m ulta_analysis.classification.cli `
  --temp-dir "data/02_temp/blush/20260724T001508Z" `
  --output-dir "data/03_color_analysis/blush/20260724T001508Z"
```

## Swatch color extraction

Color extraction is a separate, resumable processing stage. It does not change
the scraped or prepared variant dataset. The input is the class-1 `variants.csv`
produced by the preparation or classification pipeline:

```text
data/03_color_analysis/blush/<RUN_ID>/variants.csv
```

Start with a five-row verification run:

```powershell
python scripts/extract_swatch_colors.py `
  --input "data/03_color_analysis/blush/<RUN_ID>/variants.csv" `
  --output "data/03_color_analysis/blush/<RUN_ID>/swatch_colors_sample.csv" `
  --limit 5
```

Then use a new output path for the complete dataset:

```powershell
python scripts/extract_swatch_colors.py `
  --input "data/03_color_analysis/blush/20260724T001508Z/variants.csv" `                  
  --output "data/03_color_analysis/blush/20260724T001508Z/swatch_colors.csv"
```

The command checkpoints every 25 attempted images and resumes from an existing
output. Each output row is keyed by `product_id`, `sku_id`, and
`swatch_image_url` and includes:

- median center-crop RGB and a derived HEX display value;
- CIE L*a*b* coordinates under the D65 reference white;
- source-image SHA-256 and dimensions;
- sampled-pixel count and `rgb_spread` for quality review; and
- the versioned extraction method, `center_median_srgb_v1`.

The failure CSV is an attempt log, so a temporary failure remains recorded even
after a later resume succeeds. Use `unresolved_row_count` in the manifest to
determine whether any swatches are still missing.

The center crop, background rejection, and median estimator come from the most
reliable versions in the earlier Ulta projects. Manual color patches and product
exclusions are intentionally not embedded in this measurement layer. Corrections
should be a separate, auditable cleaning table.

These values describe Ulta's digital swatch artwork. They do not directly
measure the physical cosmetic, its pigment formula, lighting behavior, or its
appearance on different skin tones.

## Interactive blush color map
> This section documents the previous implementation and will be updated during the color-map redesign.

Feature 1 is generated as a self-contained HTML report. It needs no database,
GPU, web server, or Conda-specific setup; the project `.venv` and any modern
browser are sufficient.

```powershell
python scripts/build_color_map.py `
  --variants "data/processed_data/test/blushes/cleaned/cleaned_single_blush.csv" `
  --colors "data/interim/blush/swatch_colors.csv" `
  --output "reports/interactive/blush-color-map.html"
```

The X coordinate is LCh hue angle across the blush-relevant
magenta/purple-to-coral/orange arc. The Y coordinate is Lab `L*` lightness.
These positions are calculated directly from color space; no machine learning
is involved. Hover shows brand, product, variant, price, size, unit price, hue,
lightness, and chroma. Clicking pins product and swatch images plus the Ulta link
in a details panel.

Generated HTML reports are ignored by Git because they embed Plotly and can be
rebuilt from the CSV inputs. The same Plotly figure can later move into Dash
when color clustering, nearest-shade selection, and ingredient filters require
server-backed interactions.

![Feature 1: Color Map](images/feature_1_color_map.png)

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