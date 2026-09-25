from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
import IP2Location

from app.config import Settings

logger = logging.getLogger(__name__)


class GeoDatabaseError(RuntimeError):
    """Raised when the geo database cannot be downloaded or opened."""


class BinReader(Protocol):
    def get_all(self, addr: str) -> Any: ...

    def close(self) -> None: ...


def download_url(base_url: str, token: str, package_code: str) -> str:
    query = urlencode({"token": token, "file": package_code})
    return f"{base_url.rstrip('/')}?{query}"


def open_bin(path: Path | str) -> BinReader:
    return IP2Location.IP2Location(str(path))


class GeoDatabase:
    """Downloads, opens, and hot-swaps a pair of IP2Location BIN readers."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client
        self._owns_client = http_client is None
        self._ipv4_reader: BinReader | None = None
        self._ipv6_reader: BinReader | None = None
        self._previous_ipv4: BinReader | None = None
        self._previous_ipv6: BinReader | None = None
        self._etag_v4: str | None = None
        self._etag_v6: str | None = None
        self._last_modified_v4: str | None = None
        self._last_modified_v6: str | None = None

    @property
    def is_open(self) -> bool:
        return self._ipv4_reader is not None and self._ipv6_reader is not None

    def lookup_record(self, ip: str) -> Any:
        if not self.is_open:
            raise GeoDatabaseError("Geo database reader is not open")
        assert self._ipv4_reader is not None
        assert self._ipv6_reader is not None
        if ":" in ip:
            return self._ipv6_reader.get_all(ip)
        return self._ipv4_reader.get_all(ip)

    async def start(self) -> None:
        if not self.settings.ip2location_token:
            raise GeoDatabaseError("IP2LOCATION_TOKEN is required")
        try:
            await self._download_and_open_pair()
            logger.info(
                "Opened geo databases from %s and %s",
                self.settings.geo_db_ipv4_code,
                self.settings.geo_db_ipv6_code,
            )
        except Exception as exc:
            raise GeoDatabaseError(
                "Failed to download and open geo databases on start"
            ) from exc

    async def refresh(self) -> None:
        if not self.settings.ip2location_token:
            raise GeoDatabaseError("IP2LOCATION_TOKEN is required")
        try:
            swapped = await self._download_and_open_pair()
            if swapped:
                logger.info(
                    "Refreshed geo databases from %s and %s",
                    self.settings.geo_db_ipv4_code,
                    self.settings.geo_db_ipv6_code,
                )
            else:
                logger.info("Geo databases unchanged (304)")
        except Exception as exc:
            raise GeoDatabaseError("Geo database refresh failed") from exc

    async def refresh_loop(self) -> None:
        interval = self.settings.geo_db_update_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await self.refresh()
            except Exception:
                logger.exception(
                    "Geo database refresh failed; keeping the current readers"
                )

    async def close(self) -> None:
        for attr in (
            "_previous_ipv4",
            "_previous_ipv6",
            "_ipv4_reader",
            "_ipv6_reader",
        ):
            reader = getattr(self, attr)
            if reader is not None:
                reader.close()
                setattr(self, attr, None)
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

    async def _download_and_open_pair(self) -> bool:
        """Download both packages, verify, atomically replace, and swap readers.

        Returns False when both remotes responded 304 (no rewrite).
        """
        ipv4_dest = Path(self.settings.geo_db_ipv4_path)
        ipv6_dest = Path(self.settings.geo_db_ipv6_path)
        ipv4_dest.parent.mkdir(parents=True, exist_ok=True)
        ipv6_dest.parent.mkdir(parents=True, exist_ok=True)

        ipv4_url = download_url(
            self.settings.geo_db_download_base_url,
            self.settings.ip2location_token,
            self.settings.geo_db_ipv4_code,
        )
        ipv6_url = download_url(
            self.settings.geo_db_download_base_url,
            self.settings.ip2location_token,
            self.settings.geo_db_ipv6_code,
        )

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="geo-db-") as tmpdir:
            tmp = Path(tmpdir)
            v4_bin = tmp / "ipv4.bin"
            v6_bin = tmp / "ipv6.bin"

            v4_result = await self._fetch_bin(
                ipv4_url,
                v4_bin,
                ipv4_dest,
                etag=self._etag_v4,
                last_modified=self._last_modified_v4,
            )
            v6_result = await self._fetch_bin(
                ipv6_url,
                v6_bin,
                ipv6_dest,
                etag=self._etag_v6,
                last_modified=self._last_modified_v6,
            )

            if v4_result.not_modified and v6_result.not_modified:
                elapsed = time.monotonic() - started
                logger.info(
                    "Finished geo database download: not modified (304) in %.1fs",
                    elapsed,
                )
                return False

            verify_v4 = open_bin(v4_bin)
            verify_v4.close()
            verify_v6 = open_bin(v6_bin)
            verify_v6.close()

            tmp_v4 = ipv4_dest.with_name(ipv4_dest.name + ".tmp")
            tmp_v6 = ipv6_dest.with_name(ipv6_dest.name + ".tmp")
            shutil.copyfile(v4_bin, tmp_v4)
            shutil.copyfile(v6_bin, tmp_v6)
            os.replace(tmp_v4, ipv4_dest)
            os.replace(tmp_v6, ipv6_dest)

            if v4_result.etag:
                self._etag_v4 = v4_result.etag
            if v4_result.last_modified:
                self._last_modified_v4 = v4_result.last_modified
            if v6_result.etag:
                self._etag_v6 = v6_result.etag
            if v6_result.last_modified:
                self._last_modified_v6 = v6_result.last_modified

        ipv4_reader = open_bin(ipv4_dest)
        ipv6_reader = open_bin(ipv6_dest)
        self._publish_readers(ipv4_reader, ipv6_reader)
        elapsed = time.monotonic() - started
        logger.info(
            "Finished geo database download to %s (%s) and %s (%s) in %.1fs",
            ipv4_dest,
            _format_size(ipv4_dest.stat().st_size),
            ipv6_dest,
            _format_size(ipv6_dest.stat().st_size),
            elapsed,
        )
        return True

    async def _fetch_bin(
        self,
        url: str,
        dest_bin: Path,
        existing_dest: Path,
        *,
        etag: str | None,
        last_modified: str | None,
    ) -> _FetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        logger.info("Starting geo database download from package URL")
        client = await self._client()
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 304:
                if not existing_dest.exists():
                    raise GeoDatabaseError(
                        f"Remote returned 304 but local file missing: {existing_dest}"
                    )
                shutil.copyfile(existing_dest, dest_bin)
                return _FetchResult(
                    not_modified=True,
                    etag=etag,
                    last_modified=last_modified,
                )
            response.raise_for_status()
            new_etag = response.headers.get("ETag")
            new_last_modified = response.headers.get("Last-Modified")
            raw_path = dest_bin.with_suffix(".download")
            async with asyncio.timeout(180):
                with raw_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
            _extract_bin(raw_path, dest_bin)
            return _FetchResult(
                not_modified=False,
                etag=new_etag,
                last_modified=new_last_modified,
            )

    def _publish_readers(self, ipv4: BinReader, ipv6: BinReader) -> None:
        old_v4 = self._ipv4_reader
        old_v6 = self._ipv6_reader
        self._ipv4_reader = ipv4
        self._ipv6_reader = ipv6
        if self._previous_ipv4 is not None:
            self._previous_ipv4.close()
        if self._previous_ipv6 is not None:
            self._previous_ipv6.close()
        self._previous_ipv4 = old_v4
        self._previous_ipv6 = old_v6


class _FetchResult:
    __slots__ = ("not_modified", "etag", "last_modified")

    def __init__(
        self,
        *,
        not_modified: bool,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        self.not_modified = not_modified
        self.etag = etag
        self.last_modified = last_modified


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _extract_bin(raw_path: Path, dest: Path) -> None:
    """Extract a .BIN from a ZIP download, or copy a raw BIN payload."""
    if zipfile.is_zipfile(raw_path):
        with zipfile.ZipFile(raw_path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.upper().endswith(".BIN") and not name.endswith("/")
            ]
            if not members:
                raise GeoDatabaseError(f"No .BIN member in download archive: {raw_path}")
            # Prefer a top-level .BIN; otherwise take the first match.
            members.sort(key=lambda name: name.count("/"))
            with archive.open(members[0]) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
        return
    shutil.copyfile(raw_path, dest)
