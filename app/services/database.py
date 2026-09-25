from __future__ import annotations

import asyncio
import gzip
import logging
import os
import shutil
import tempfile
import time
from calendar import monthrange
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import maxminddb

from app.config import Settings

logger = logging.getLogger(__name__)

MONTH_PLACEHOLDER = "{YYYY-MM}"


class GeoDatabaseError(RuntimeError):
    """Raised when the geo database cannot be downloaded or opened."""


def resolve_url(template: str, year_month: datetime | None = None) -> str:
    """Replace `{YYYY-MM}` with a UTC year-month. Literal URLs are returned as-is."""
    if MONTH_PLACEHOLDER not in template:
        return template
    when = year_month or datetime.now(UTC)
    return template.replace(MONTH_PLACEHOLDER, when.strftime("%Y-%m"))


def previous_utc_month(when: datetime | None = None) -> datetime:
    current = when or datetime.now(UTC)
    year = current.year
    month = current.month - 1
    if month == 0:
        month = 12
        year -= 1
    last_day = monthrange(year, month)[1]
    day = min(current.day, last_day)
    return current.replace(year=year, month=month, day=day)


def start_urls(template: str, when: datetime | None = None) -> list[str]:
    """Current-month URL, then previous-month when the template is dated."""
    current = when or datetime.now(UTC)
    current_url = resolve_url(template, current)
    if MONTH_PLACEHOLDER not in template:
        return [current_url]
    previous_url = resolve_url(template, previous_utc_month(current))
    if previous_url == current_url:
        return [current_url]
    return [current_url, previous_url]


class GeoDatabase:
    """Downloads, opens, and hot-swaps an MMDB reader."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client
        self._owns_client = http_client is None
        self._reader: maxminddb.Reader | None = None
        self._previous_reader: maxminddb.Reader | None = None
        self._etag: str | None = None
        self._last_modified: str | None = None

    @property
    def is_open(self) -> bool:
        return self._reader is not None

    def get_reader(self) -> maxminddb.Reader | None:
        """Return the current reader snapshot for an in-flight lookup."""
        return self._reader

    def lookup_record(self, ip: str) -> Any:
        reader = self._reader
        if reader is None:
            raise GeoDatabaseError("Geo database reader is not open")
        return reader.get(ip)

    async def start(self) -> None:
        last_error: Exception | None = None
        for url in start_urls(self.settings.geo_db_url):
            try:
                await self._download_and_open(url)
                logger.info("Opened geo database from %s", url)
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Start download failed for %s: %s", url, exc)
        raise GeoDatabaseError(
            "Failed to download and open a geo database on start"
        ) from last_error

    async def refresh(self) -> None:
        last_error: Exception | None = None
        for url in start_urls(self.settings.geo_db_url):
            try:
                swapped = await self._download_and_open(url)
                if swapped:
                    logger.info("Refreshed geo database from %s", url)
                else:
                    logger.info("Geo database unchanged (304) for %s", url)
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Refresh download failed for %s: %s", url, exc)
        raise GeoDatabaseError("Geo database refresh failed") from last_error

    async def refresh_loop(self) -> None:
        interval = self.settings.geo_db_update_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await self.refresh()
            except Exception:
                logger.exception(
                    "Geo database refresh failed; keeping the current reader"
                )

    async def close(self) -> None:
        if self._previous_reader is not None:
            self._previous_reader.close()
            self._previous_reader = None
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(120.0),
            )
        return self._http_client

    async def _download_and_open(self, url: str) -> bool:
        """Download, verify, atomically replace, and swap the reader.

        Returns False when the remote responded 304 (no rewrite).
        """
        dest = Path(self.settings.geo_db_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified

        logger.info("Starting geo database download from %s", url)
        started = time.monotonic()
        client = await self._client()
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 304:
                elapsed = time.monotonic() - started
                logger.info(
                    "Finished geo database download from %s: not modified (304) in %.1fs",
                    url,
                    elapsed,
                )
                return False
            response.raise_for_status()
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
            with tempfile.TemporaryDirectory(prefix="geo-db-") as tmpdir:
                raw_path = Path(tmpdir) / "download.bin"
                async with asyncio.timeout(180):
                    with raw_path.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            handle.write(chunk)
                tmp_dest = dest.with_name(dest.name + ".tmp")
                _extract_mmdb(url, raw_path, tmp_dest)
                verify = maxminddb.open_database(tmp_dest)
                verify.close()
                os.replace(tmp_dest, dest)

        reader = maxminddb.open_database(dest)
        self._publish_reader(reader)
        if etag:
            self._etag = etag
        if last_modified:
            self._last_modified = last_modified
        elapsed = time.monotonic() - started
        size = dest.stat().st_size if dest.exists() else 0
        logger.info(
            "Finished geo database download from %s to %s (%s in %.1fs)",
            url,
            dest,
            _format_size(size),
            elapsed,
        )
        return True

    def _publish_reader(self, reader: maxminddb.Reader) -> None:
        old = self._reader
        self._reader = reader
        if self._previous_reader is not None:
            self._previous_reader.close()
        self._previous_reader = old


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _extract_mmdb(url: str, raw_path: Path, dest: Path) -> None:
    if url.endswith(".gz") or raw_path.suffix == ".gz":
        with gzip.open(raw_path, "rb") as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)
        return
    shutil.copyfile(raw_path, dest)
