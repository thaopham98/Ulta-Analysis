"""Build a standalone interactive Lab/LCh blush color map."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import plotly.graph_objects as go


REQUIRED_VARIANT_FIELDS = {
    "product_id",
    "sku_id",
    "brand",
    "product_name",
    "variant_name",
    "variant_url",
    "swatch_image_url",
    "variant_image_url",
    "effective_price",
    "size_value",
    "size_unit",
    "price_per_g_ml",
}

REQUIRED_COLOR_FIELDS = {
    "product_id",
    "sku_id",
    "hex_color",
    "lab_l",
    "lab_a",
    "lab_b",
}


def build_color_map(
    variants_path: str | Path,
    colors_path: str | Path,
    output_path: str | Path,
    *,
    include_plotlyjs: bool | str = True,
) -> Path:
    """Join SKU tables and write a self-contained interactive HTML report."""
    variants = _read_csv(Path(variants_path), REQUIRED_VARIANT_FIELDS)
    colors = _read_csv(Path(colors_path), REQUIRED_COLOR_FIELDS)
    rows = _join_by_sku(variants, colors)
    if not rows:
        raise ValueError("No matching SKU rows were found")

    for row in rows:
        lab_a = _required_float(row, "lab_a")
        lab_b = _required_float(row, "lab_b")
        row["lab_l_value"] = _required_float(row, "lab_l")
        row["hue_angle"] = math.degrees(math.atan2(lab_b, lab_a))
        row["chroma"] = math.hypot(lab_a, lab_b)

    rows.sort(key=lambda row: (row["hue_angle"], row["lab_l_value"], row["sku_id"]))
    figure = _build_figure(rows)
    plot_html = figure.to_html(
        full_html=False,
        include_plotlyjs=include_plotlyjs,
        config={
            "displaylogo": False,
            "responsive": True,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
        div_id="ulta-color-map-plot",
        post_script=_selection_script(),
    )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(_page_html(plot_html, len(rows)), encoding="utf-8")
    temporary.replace(destination)
    return destination


def _build_figure(rows: list[dict]) -> go.Figure:
    customdata = [
        [
            row.get("brand") or "Unknown brand",
            row.get("product_name") or "Unknown product",
            row.get("variant_name") or "Unnamed shade",
            _price_text(row.get("effective_price")),
            _size_text(row),
            _unit_price_text(row),
            row.get("variant_url") or "",
            row.get("variant_image_url") or "",
            row.get("swatch_image_url") or "",
            row["sku_id"],
            round(row["chroma"], 2),
            round(_required_float(row, "lab_a"), 2),
            round(_required_float(row, "lab_b"), 2),
        ]
        for row in rows
    ]
    figure = go.Figure(
        go.Scattergl(
            x=[round(row["hue_angle"], 3) for row in rows],
            y=[round(row["lab_l_value"], 3) for row in rows],
            mode="markers",
            customdata=customdata,
            marker={
                "color": [row["hex_color"] for row in rows],
                "size": 9,
                "opacity": 0.82,
                "line": {"color": "rgba(35,35,35,0.35)", "width": 0.6},
            },
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Shade: %{customdata[2]}<br>"
                "Price: %{customdata[3]}<br>"
                "Size: %{customdata[4]}<br>"
                "Unit price: %{customdata[5]}<br>"
                "Hue: %{x:.1f}° · L*: %{y:.1f} · C*: %{customdata[10]:.1f}"
                "<extra>Click to pin details</extra>"
            ),
        )
    )
    hue_values = [row["hue_angle"] for row in rows]
    lightness_values = [row["lab_l_value"] for row in rows]
    figure.update_layout(
        template="plotly_white",
        autosize=True,
        height=700,
        margin={"l": 70, "r": 30, "t": 55, "b": 75},
        hovermode="closest",
        dragmode="pan",
        xaxis={
            "title": "Hue angle h° — cooler magenta/purple ← → warmer coral/orange",
            "range": [math.floor(min(hue_values) - 5), math.ceil(max(hue_values) + 5)],
            "zeroline": True,
            "zerolinecolor": "rgba(90,90,90,0.45)",
            "gridcolor": "rgba(120,120,120,0.14)",
        },
        yaxis={
            "title": "Lightness L* — dark ← → light",
            "range": [max(0, math.floor(min(lightness_values) - 4)), min(100, math.ceil(max(lightness_values) + 4))],
            "gridcolor": "rgba(120,120,120,0.14)",
        },
    )
    return figure


def _selection_script() -> str:
    return r"""
const plot = document.getElementById('ulta-color-map-plot');
const setText = (id, value) => {
  document.getElementById(id).textContent = value || 'Not available';
};
const setImage = (id, url, alt) => {
  const image = document.getElementById(id);
  if (!url) {
    image.hidden = true;
    image.removeAttribute('src');
    return;
  }
  image.src = url;
  image.alt = alt;
  image.hidden = false;
};
plot.on('plotly_click', (event) => {
  const point = event.points[0];
  const data = point.customdata;
  setText('ulta-detail-brand', data[0]);
  setText('ulta-detail-product', data[1]);
  setText('ulta-detail-variant', data[2]);
  setText('ulta-detail-price', data[3]);
  setText('ulta-detail-size', data[4]);
  setText('ulta-detail-unit-price', data[5]);
  setText('ulta-detail-color', `${point.data.marker.color[point.pointNumber]} | hue ${point.x.toFixed(1)} deg | L* ${point.y.toFixed(1)} | C* ${Number(data[10]).toFixed(1)}`);
  setImage('ulta-detail-product-image', data[7], `${data[0]} ${data[1]} ${data[2]}`);
  setImage('ulta-detail-swatch-image', data[8], `${data[2]} swatch`);
  const link = document.getElementById('ulta-detail-link');
  link.href = data[6];
  link.hidden = !data[6];
  document.getElementById('ulta-detail-empty').hidden = true;
  document.getElementById('ulta-detail-content').hidden = false;
});
"""


def _page_html(plot_html: str, row_count: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ulta blush color map</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f5f3; color: #241f20; }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: clamp(1.5rem, 3vw, 2.25rem); font-weight: 650; }}
    .subtitle {{ margin: 0 0 20px; color: #665d60; }}
    .layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start; }}
    .plot-shell, .details {{ background: #fff; border: 1px solid #ded8d9; border-radius: 14px; box-shadow: 0 8px 28px rgba(43, 30, 35, 0.06); }}
    .plot-shell {{ min-width: 0; overflow: hidden; }}
    .details {{ padding: 18px; position: sticky; top: 18px; }}
    .details h2 {{ margin: 0 0 14px; font-size: 1rem; }}
    .empty {{ color: #746a6d; line-height: 1.5; }}
    .images {{ display: grid; grid-template-columns: 1fr 72px; gap: 10px; margin-bottom: 16px; align-items: end; }}
    .product-image, .swatch-image {{ display: block; width: 100%; border-radius: 10px; background: #f3eff0; object-fit: cover; }}
    .product-image {{ aspect-ratio: 1; }}
    .swatch-image {{ aspect-ratio: 1; }}
    .brand {{ margin: 0; color: #6b6164; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    .product {{ margin: 4px 0; font-size: 1.08rem; font-weight: 650; line-height: 1.3; }}
    .variant {{ margin: 0 0 16px; color: #544a4d; }}
    dl {{ display: grid; grid-template-columns: 92px 1fr; gap: 8px 10px; margin: 0 0 18px; font-size: 0.9rem; }}
    dt {{ color: #766c6f; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .link {{ display: inline-block; color: #7f284d; font-weight: 650; text-decoration: none; }}
    .link:hover {{ text-decoration: underline; }}
    @media (max-width: 900px) {{
      main {{ padding: 14px; }}
      .layout {{ grid-template-columns: 1fr; }}
      .details {{ position: static; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Ulta blush color map</h1>
    <p class="subtitle">{row_count:,} digital swatches positioned by CIE LCh hue and Lab lightness. Hover to inspect; click to pin product details.</p>
    <div class="layout">
      <section class="plot-shell" aria-label="Interactive blush color map">
        {plot_html}
      </section>
      <aside class="details" aria-live="polite">
        <h2>Selected shade</h2>
        <p id="ulta-detail-empty" class="empty">Click any color point to keep its product details here.</p>
        <div id="ulta-detail-content" hidden>
          <div class="images">
            <img id="ulta-detail-product-image" class="product-image" alt="" hidden>
            <img id="ulta-detail-swatch-image" class="swatch-image" alt="" hidden>
          </div>
          <p id="ulta-detail-brand" class="brand"></p>
          <p id="ulta-detail-product" class="product"></p>
          <p id="ulta-detail-variant" class="variant"></p>
          <dl>
            <dt>Price</dt><dd id="ulta-detail-price"></dd>
            <dt>Size</dt><dd id="ulta-detail-size"></dd>
            <dt>Unit price</dt><dd id="ulta-detail-unit-price"></dd>
            <dt>Color</dt><dd id="ulta-detail-color"></dd>
          </dl>
          <a id="ulta-detail-link" class="link" href="#" target="_blank" rel="noopener noreferrer" hidden>View on Ulta</a>
        </div>
      </aside>
    </div>
  </main>
</body>
</html>
"""


def _read_csv(path: Path, required_fields: set[str]) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"CSV does not exist: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required_fields.difference(fields)
        if missing:
            raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
        return list(reader)


def _join_by_sku(variants: list[dict], colors: list[dict]) -> list[dict]:
    variant_by_sku = _unique_by_sku(variants, "variant table")
    color_by_sku = _unique_by_sku(colors, "color table")
    missing_details = sorted(set(color_by_sku).difference(variant_by_sku))
    missing_colors = sorted(set(variant_by_sku).difference(color_by_sku))
    if missing_details or missing_colors:
        raise ValueError(
            "SKU join is incomplete: "
            f"{len(missing_details)} colors lack variant details and "
            f"{len(missing_colors)} variants lack colors"
        )
    return [
        {**variant_by_sku[sku_id], **color_by_sku[sku_id]}
        for sku_id in variant_by_sku
    ]


def _unique_by_sku(rows: list[dict], label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        sku_id = (row.get("sku_id") or "").strip()
        if not sku_id:
            raise ValueError(f"{label} contains an empty sku_id")
        if sku_id in result:
            raise ValueError(f"{label} contains duplicate SKU {sku_id}")
        result[sku_id] = row
    return result


def _required_float(row: dict, field: str) -> float:
    try:
        return float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"SKU {row.get('sku_id', '?')} has invalid {field}") from error


def _price_text(value: str | None) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Not available"


def _size_text(row: dict) -> str:
    value = (row.get("size_value") or "").strip()
    unit = (row.get("size_unit") or "").strip()
    return f"{value} {unit}".strip() or "Not available"


def _unit_price_text(row: dict) -> str:
    value = row.get("price_per_g_ml")
    unit = (row.get("size_unit") or "").casefold()
    denominator = "mL" if unit in {"ml", "fl oz"} else "g"
    try:
        return f"${float(value):,.2f}/{denominator}"
    except (TypeError, ValueError):
        return "Not available"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a standalone interactive Ulta blush color map."
    )
    parser.add_argument("--variants", required=True, help="Cleaned single-blush CSV.")
    parser.add_argument("--colors", required=True, help="Extracted swatch-colors CSV.")
    parser.add_argument("--output", required=True, help="Destination HTML file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = build_color_map(args.variants, args.colors, args.output)
    except (OSError, TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"Interactive color map: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
