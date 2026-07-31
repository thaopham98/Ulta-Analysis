# Data directories

`raw/` contains immutable, timestamped schema-v2 scrape outputs:

```text
raw/{collection}/{run_id}/
  run_manifest.json
  collection_products.csv
  products.csv
  variants.csv
  ingredients.csv
  failures.csv
  checkpoint.json
```

One run folder holds the complete collection. Ingredient text is stored once
per distinct product formula in `ingredients.csv`; `variants.csv` links each
SKU to its formula with `ingredient_set_id`.

Future pipeline stages should use:

- `interim/` for resumable caches and normalized-but-not-final data;
- `processed/` for validated analysis-ready tables.

Never overwrite a completed raw run. Start a new run so price, availability,
formula, and catalog changes remain observable over time. Historical schema-v1
snapshots remain valid records but cannot be resumed by the schema-v2 scraper.
