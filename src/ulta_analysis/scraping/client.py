"""Rate-limited HTTP client with bounded retries."""

from __future__ import annotations

import re
import time
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ulta_analysis.config import ScrapeConfig


class UltaClient:
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self.session = requests.Session()
        retry = Retry(
            total=config.max_retries,
            connect=config.max_retries,
            read=config.max_retries,
            status=config.max_retries,
            backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
            }
        )
        self._last_request_at: float | None = None

    def get_text(self, url: str) -> str:
        self._wait_for_rate_limit()
        response = self.session.get(
            url,
            timeout=self.config.timeout_seconds,
            allow_redirects=True,
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError(
                f"Expected HTML from {url}, got "
                f"{response.headers.get('Content-Type', 'unknown content type')}"
            )
        declared = _declared_charset(response.headers.get("Content-Type", ""))
        return decode_html(
            response.content,
            declared_encoding=declared,
            apparent_encoding=response.apparent_encoding,
        )

    def close(self) -> None:
        self.session.close()

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.config.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def __enter__(self) -> "UltaClient":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


def decode_html(
    content: bytes,
    *,
    declared_encoding: str | None = None,
    apparent_encoding: str | None = None,
) -> str:
    """Decode without replacement characters and normalize text to Unicode NFC."""
    candidates = ["utf-8", declared_encoding, apparent_encoding]
    attempted: list[str] = []
    for encoding in candidates:
        if not encoding or encoding.casefold() in {
            item.casefold() for item in attempted
        }:
            continue
        attempted.append(encoding)
        try:
            return unicodedata.normalize(
                "NFC",
                content.decode(encoding, errors="strict"),
            )
        except (LookupError, UnicodeDecodeError):
            continue
    raise UnicodeError(
        "Unable to decode Ulta HTML without data loss; attempted "
        + ", ".join(attempted)
    )


def _declared_charset(content_type: str) -> str | None:
    match = re.search(r"\bcharset\s*=\s*[\"']?([^;\"'\s]+)", content_type, re.I)
    return match.group(1) if match else None
