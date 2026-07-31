"""Load shared scraper settings and named Ulta collections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import tomllib
from urllib.parse import urlparse


COLLECTION_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
SOURCE_TYPES = {"auto", "listing", "product"}


@dataclass(frozen=True)
class ScraperSettings:
    request_delay_seconds: float = 1.0
    checkpoint_interval: int = 25
    max_pages: int = 100
    timeout_seconds: int = 20
    max_retries: int = 3
    user_agent: str = (
        "UltaAnalysisResearch/0.2 "
        "(+personal market research; respectful request rate)"
    )


@dataclass(frozen=True)
class ScrapeConfig:
    name: str
    source_url: str
    source_type: str = "auto"
    request_delay_seconds: float = 1.0
    checkpoint_interval: int = 25
    max_pages: int = 100
    timeout_seconds: int = 20
    max_retries: int = 3
    user_agent: str = (
        "UltaAnalysisResearch/0.2 "
        "(+personal market research; respectful request rate)"
    )

    @property
    def resolved_source_type(self) -> str:
        if self.source_type != "auto":
            return self.source_type
        return "product" if urlparse(self.source_url).path.startswith("/p/") else "listing"

    def to_dict(self) -> dict:
        values = asdict(self)
        values["resolved_source_type"] = self.resolved_source_type
        return values


def load_scraper_settings(path: str | Path) -> ScraperSettings:
    with Path(path).open("rb") as handle:
        document = tomllib.load(handle)
    values = document.get("scraper")
    if not isinstance(values, dict):
        raise ValueError("scraper.toml must contain a [scraper] table")
    settings = ScraperSettings(**values)
    _validate_settings(settings)
    return settings


def load_collection(
    settings_path: str | Path,
    collections_path: str | Path,
    name: str,
) -> ScrapeConfig:
    if not COLLECTION_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "collection name must contain only lowercase letters, numbers, "
            "hyphens, and underscores, and cannot start with punctuation"
        )
    settings = load_scraper_settings(settings_path)
    with Path(collections_path).open("rb") as handle:
        document = tomllib.load(handle)
    collections = document.get("collections")
    if not isinstance(collections, dict):
        raise ValueError("collections.toml must contain [collections.*] tables")
    values = collections.get(name)
    if not isinstance(values, dict):
        available = ", ".join(sorted(collections)) or "(none)"
        raise ValueError(f"Unknown collection {name!r}. Available: {available}")
    config = ScrapeConfig(name=name, **asdict(settings), **values)
    _validate_config(config)
    return config


def collection_names(path: str | Path) -> tuple[str, ...]:
    with Path(path).open("rb") as handle:
        collections = tomllib.load(handle).get("collections", {})
    if not isinstance(collections, dict):
        raise ValueError("collections.toml must contain [collections.*] tables")
    return tuple(sorted(collections))


def validate_config(config: ScrapeConfig) -> ScrapeConfig:
    _validate_config(config)
    return config


def _validate_settings(settings: ScraperSettings | ScrapeConfig) -> None:
    if settings.request_delay_seconds < 0:
        raise ValueError("request_delay_seconds cannot be negative")
    if settings.checkpoint_interval < 1:
        raise ValueError("checkpoint_interval must be at least 1")
    if settings.max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if settings.timeout_seconds < 1:
        raise ValueError("timeout_seconds must be at least 1")
    if settings.max_retries < 0:
        raise ValueError("max_retries cannot be negative")


def _validate_config(config: ScrapeConfig) -> None:
    _validate_settings(config)
    parsed = urlparse(config.source_url)
    if parsed.scheme != "https" or parsed.hostname not in {"ulta.com", "www.ulta.com"}:
        raise ValueError("source_url must be an https Ulta URL")
    if not COLLECTION_NAME_PATTERN.fullmatch(config.name):
        raise ValueError("invalid collection name")
    if config.source_type not in SOURCE_TYPES:
        raise ValueError("source_type must be auto, listing, or product")
    if config.resolved_source_type == "product" and not parsed.path.startswith("/p/"):
        raise ValueError("product source_type requires an Ulta /p/ product URL")
    if config.resolved_source_type == "listing" and not parsed.path.startswith("/shop/"):
        raise ValueError("listing source_type requires an Ulta /shop/ URL")
