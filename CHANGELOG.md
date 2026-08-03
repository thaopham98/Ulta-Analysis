# Change log

All material workspace changes are recorded here for future review.

## 2026-08-03 — Feature 1 interactive color-space map

### Added

- A standalone Plotly HTML generator that joins cleaned product details to
  swatch colors by unique `sku_id`.
- Deterministic LCh hue-angle and Lab-lightness positioning for 1,363 blush
  shades; no clustering or machine learning is used for coordinates.
- Hover details and a click-pinned panel with product/swatch images, pricing,
  normalized unit price, and Ulta links.
- Strict one-to-one SKU join validation and automated report tests.

The report is deliberately serverless for the first feature. A Dash application
can reuse the figure later when recommendations and filters are implemented.

## 2026-07-31 — Resumable swatch color measurement

### Added

- A dedicated `ulta_analysis.colors` package and `extract_swatch_colors.py`
  entry point.
- Center-crop median RGB extraction with transparent/near-white background
  handling, derived HEX, and sRGB-to-CIE-Lab conversion under D65.
- Image hashes, dimensions, sampled-pixel counts, RGB spread, atomic
  checkpoints, failure logs, and run manifests.
- Tests against prior cached Lab values, solid swatches, white backgrounds, and
  resume behavior.

### Prior-project review

- `Ulta_Project` contained the strongest reusable implementation: center 20%
  crop, channel-wise median RGB, and Lab conversion.
- `new_ulta_v2` added near-white background rejection but mixed color
  extraction with text repair, product exclusions, and destructive row drops.
- `ulta_pigments` stored two dominant HEX values and seasonal labels but did
  not provide a clean reproducible extraction stage.
- `Ulta` converted extracted RGB values to Lab for clustering, but clustering
  remains a later analysis stage and was not copied into collection code.

## 2026-07-23 — Ingredient-focused normalized raw schema

### Changed

- Replaced per-collection config files with `configs/scraper.toml` and
  `configs/collections.toml`.
- Replaced the denormalized `shade_records.csv` output with collection
  inventory, product, variant, and deduplicated ingredient tables.
- Removed summary, details, how-to-use, currency, repeated source fields, and
  row-level observation timestamps from the raw contract.
- Renamed the product image field to `variant_image_url`.
- Added strict HTML decoding, Unicode NFC normalization, UTF-8-SIG CSV output,
  and accented-text round-trip tests.
- Kept run timing and collection provenance once in `run_manifest.json`.

Schema-v1 snapshots were not modified. New and resumed runs use schema v2;
schema-v1 runs intentionally cannot be resumed into the new table contract.

## 2026-07-22 — Reusable Ulta collections and consolidated raw storage

### Changed

- `src/ulta_analysis/config.py`
  - Generalized `category_url` to `source_url`.
  - Added `source_type` (`listing`, `product`, or automatic detection).
  - Retained compatibility with older TOML files that use `category_url`.
  - Added safe collection-name and Ulta URL validation.
  - Raised the listing-page safety cap from 12 to 100 so broad collections
    such as all moisturizers are not silently truncated if Ulta paginates them.
- `src/ulta_analysis/scraping/scraper.py`
  - Added listing/product dispatch. A direct `/p/` URL becomes a one-product
    inventory without trying to parse it as a category page.
  - Added collection/source metadata to each raw record and the run manifest.
  - Added resume validation against the original collection and source URL.
- `src/ulta_analysis/scraping/cli.py`
  - Added `--url` and `--name` for future one-off collections.
- `src/ulta_analysis/scraping/parsers.py` and
  `src/ulta_analysis/schemas.py`
  - Replaced the blush-specific `category` raw field with general `collection`
    and `collection_source_url` fields.
- `configs/blush.toml`
  - Migrated to the reusable source configuration.
- `README.md` and `data/README.md`
  - Documented the multi-collection workflow, scalable raw layout, safe sample
    runs, direct-product behavior, and resume rules.

### Added

- Repeatable configs for bronzer, tinted moisturizer, face moisturizer, all
  moisturizers, bath & shower, the full shampoo listing, and the supplied Curl
  Talk shampoo product.
- `tests/test_scraper.py` for listing dispatch, product dispatch, and the
  consolidated run output.
- Additional config and parser coverage in the existing tests.
- This `CHANGELOG.md`.

### Raw-data decision

New runs use:

```text
data/raw/{collection}/{run_id}/
```

Each run contains a single `shade_records.csv` for all product/SKU records plus
the inventory, manifest, failure log, and checkpoint. Existing raw snapshots
were left untouched.

### Verification

- Confirmed the seven supplied Ulta URLs and the added full shampoo listing URL
  resolve to the intended live listing or product page on 2026-07-22.
- Created a repository-local, ignored `.venv` and installed the dependencies
  declared in `pyproject.toml`.
- `python -m unittest discover -s tests -v`: 14 tests passed.
- `python -m compileall -q src tests scripts`: passed.
