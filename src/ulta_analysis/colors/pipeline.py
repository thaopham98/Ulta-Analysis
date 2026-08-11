"""Resumable CSV pipeline for Ulta swatch color extraction."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time
from typing import Callable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ulta_analysis.scraping.checkpoint import (
    read_csv_rows,
    write_csv_atomic,
    write_json_atomic,
)

from .extraction import EXTRACTION_METHOD, measure_swatch_bytes

## columns for the new output files
COLOR_FIELDS = (
    "product_id",
    "sku_id",
    "swatch_image_url",
    "image_sha256",
    "image_width",
    "image_height",
    "sample_pixel_count",
    "rgb_r",
    "rgb_g",
    "rgb_b",
    "hex_color",
    "lab_l",
    "lab_a",
    "lab_b",
    "rgb_spread",
    "extraction_method",
)

## columns for the failed output files
COLOR_FAILURE_FIELDS = (
    "product_id",
    "sku_id",
    "swatch_image_url",
    "error_type",
    "message",
)

ALLOWED_SWATCH_HOSTS = {"media.ultainc.com", "media.ulta.com"} # swatch_image_url


class SwatchClient:
    """Retry-bounded client restricted to Ulta media hosts."""

    def __init__(self, *, timeout_seconds: int = 20, max_retries: int = 3):
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session() # sets up a requests.Session with strict rules
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504), # uses Retry to automatically back off and retry upon hitting rate limits (HTTP 429) or server errors (500-level codes)
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (compatible; UltaAnalysisResearch/0.2)"}
        )

    ## stream the image in chunks and enforces a hard 10MB safety limit (maxium_bytes = 10_000_000)
    ## this products against malformed or maliciously large files
    def get_bytes(self, url: str, *, maximum_bytes: int = 10_000_000) -> bytes:
        _validate_swatch_url(url)
        chunks: list[bytes] = []
        size = 0
        with self.session.get(
            url,
            timeout=self.timeout_seconds,
            allow_redirects=True,
            stream=True,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").casefold()
            if not content_type.startswith("image/"):
                raise ValueError(f"Expected an image, received {content_type or 'unknown'}")
            _validate_swatch_url(response.url)
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError("Swatch image exceeds the 10 MB safety limit")
                chunks.append(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        self.session.close() # safely close the session


def run_color_extraction(
    input_path: str | Path,
    output_path: str | Path,
    *,
    failures_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    limit: int | None = None,
    request_delay_seconds: float = 0.05,
    checkpoint_interval: int = 25,
    resume: bool = True,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> dict:
    """Extract swatch colors without modifying the prepared input dataset."""
    source = Path(input_path)
    output = Path(output_path)
    failures = Path(failures_path) if failures_path else output.with_name(
        f"{output.stem}_failures.csv"
    )
    manifest = Path(manifest_path) if manifest_path else output.with_name(
        f"{output.stem}_manifest.json"
    )
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")
    if request_delay_seconds < 0:
        raise ValueError("request_delay_seconds cannot be negative")
    if checkpoint_interval < 1:
        raise ValueError("checkpoint_interval must be at least 1")
    if not source.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {source}")
    if output.exists() and not resume:
        raise FileExistsError(f"Output exists; use resume mode or a new path: {output}")

    input_rows = _load_input_rows(source)
    if limit is not None:
        input_rows = input_rows[:limit]
    input_keys = {
        (row["sku_id"], row["swatch_image_url"])
        for row in input_rows
    }
    color_rows = read_csv_rows(output) if resume else []
    failure_rows = read_csv_rows(failures) if resume else []
    completed = {
        (row.get("sku_id", ""), row.get("swatch_image_url", ""))
        for row in color_rows
    }
    stale_keys = completed.difference(input_keys)
    if stale_keys:
        raise ValueError(
            "Existing output contains rows outside this input selection; "
            "use a new output path"
        )
    started_at = _iso_z()
    client = None if fetch_bytes else SwatchClient()
    fetcher = fetch_bytes or client.get_bytes
    starting_failure_count = len(failure_rows)
    attempted = 0
    succeeded = 0

    try:
        for row in input_rows:
            key = (row["sku_id"], row["swatch_image_url"])
            if key in completed:
                continue
            attempted += 1
            try:
                content = fetcher(row["swatch_image_url"])
                measurement = measure_swatch_bytes(content)
                color_rows.append(
                    {
                        "product_id": row.get("product_id", ""),
                        "sku_id": row["sku_id"],
                        "swatch_image_url": row["swatch_image_url"],
                        **measurement.to_dict(),
                    }
                )
                completed.add(key)
                succeeded += 1
            except Exception as error:
                failure_rows.append(
                    {
                        "product_id": row.get("product_id", ""),
                        "sku_id": row["sku_id"],
                        "swatch_image_url": row["swatch_image_url"],
                        "error_type": type(error).__name__,
                        "message": str(error)[:1000],
                    }
                )

            if attempted % checkpoint_interval == 0:
                write_csv_atomic(output, color_rows, COLOR_FIELDS)
                write_csv_atomic(failures, failure_rows, COLOR_FAILURE_FIELDS)
                print(
                    f"[colors] {len(completed)}/{len(input_rows)} complete; "
                    f"{len(failure_rows) - starting_failure_count} failures this run"
                )
            if request_delay_seconds:
                time.sleep(request_delay_seconds)
    finally:
        if client:
            client.close()

    write_csv_atomic(output, color_rows, COLOR_FIELDS)
    write_csv_atomic(failures, failure_rows, COLOR_FAILURE_FIELDS)
    result = {
        "started_at": started_at,
        "finished_at": _iso_z(),
        "status": "complete" if len(completed) == len(input_rows) else "partial",
        "input_path": str(source.resolve()),
        "input_sha256": _file_sha256(source),
        "output_path": str(output.resolve()),
        "extraction_method": EXTRACTION_METHOD,
        "input_row_count": len(input_rows),
        "completed_row_count": len(completed),
        "unresolved_row_count": len(input_rows) - len(completed),
        "attempted_this_run": attempted,
        "succeeded_this_run": succeeded,
        "failed_this_run": len(failure_rows) - starting_failure_count,
        "failure_attempt_count": len(failure_rows),
        "color_fields": list(COLOR_FIELDS),
    }
    write_json_atomic(manifest, result)
    return result


def _load_input_rows(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = {"sku_id", "swatch_image_url"}.difference(fields)
        if missing:
            raise ValueError(f"Input CSV is missing columns: {sorted(missing)}")
        rows = list(reader)

    seen: dict[str, str] = {}
    unique: list[dict] = []
    for number, row in enumerate(rows, start=2):
        sku_id = row.get("sku_id", "").strip()
        url = row.get("swatch_image_url", "").strip()
        if not sku_id or not url:
            raise ValueError(f"Missing sku_id or swatch_image_url on CSV row {number}")
        _validate_swatch_url(url)
        if sku_id in seen and seen[sku_id] != url:
            raise ValueError(f"SKU {sku_id} has more than one swatch URL")
        if sku_id in seen:
            continue
        seen[sku_id] = url
        row["sku_id"] = sku_id
        row["swatch_image_url"] = url
        unique.append(row)
    return unique


def _validate_swatch_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SWATCH_HOSTS:
        raise ValueError("swatch_image_url must use HTTPS on an Ulta media host")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )
