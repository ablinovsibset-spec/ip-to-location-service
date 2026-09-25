import io
import zipfile
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.database import GeoDatabase, GeoDatabaseError, download_url


def test_download_url_includes_token_and_code():
    url = download_url(
        "https://www.ip2location.com/download",
        "secret",
        "DB3LITEBIN",
    )
    assert url.startswith("https://www.ip2location.com/download?")
    assert "token=secret" in url
    assert "file=DB3LITEBIN" in url


def _zip_with_bin(name: str = "IP2LOCATION-LITE-DB3.BIN", payload: bytes = b"BINDATA") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, payload)
    return buffer.getvalue()


def _handler_factory(routes: dict[str, httpx.Response], seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        package = request.url.params.get("file")
        if package is not None and package in routes:
            return routes[package]
        return httpx.Response(404, text="missing")

    return handler


@pytest.mark.asyncio
async def test_start_requires_token(settings, monkeypatch):
    settings.ip2location_token = ""
    db = GeoDatabase(settings)
    with pytest.raises(GeoDatabaseError, match="IP2LOCATION_TOKEN"):
        await db.start()


@pytest.mark.asyncio
async def test_start_downloads_both_packages(settings, monkeypatch):
    seen: list[httpx.Request] = []
    routes = {
        "DB3LITEBIN": httpx.Response(
            200,
            content=_zip_with_bin("IP2LOCATION-LITE-DB3.BIN", b"v4"),
            headers={"ETag": '"v4"', "Content-Type": "application/zip"},
        ),
        "DB3LITEBINIPV6": httpx.Response(
            200,
            content=_zip_with_bin("IP2LOCATION-LITE-DB3.IPV6.BIN", b"v6"),
            headers={"ETag": '"v6"', "Content-Type": "application/zip"},
        ),
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler_factory(routes, seen)))
    db = GeoDatabase(settings, http_client=client)

    readers: list[MagicMock] = []

    def fake_open(_path):
        reader = MagicMock(name="reader")
        readers.append(reader)
        return reader

    monkeypatch.setattr("app.services.database.open_bin", fake_open)

    await db.start()
    assert db.is_open
    codes = [str(req.url) for req in seen]
    assert any("DB3LITEBIN" in url and "DB3LITEBINIPV6" not in url for url in codes)
    assert any("DB3LITEBINIPV6" in url for url in codes)
    await db.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_start_fails_when_one_package_missing(settings, monkeypatch):
    seen: list[httpx.Request] = []
    routes = {
        "DB3LITEBIN": httpx.Response(
            200,
            content=_zip_with_bin(),
            headers={"ETag": '"v4"'},
        ),
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler_factory(routes, seen)))
    db = GeoDatabase(settings, http_client=client)
    monkeypatch.setattr(
        "app.services.database.open_bin",
        lambda path: MagicMock(name="reader"),
    )

    with pytest.raises(GeoDatabaseError):
        await db.start()
    assert not db.is_open
    await client.aclose()


@pytest.mark.asyncio
async def test_refresh_keeps_old_readers_on_failure(settings, monkeypatch):
    original_v4 = MagicMock(name="original_v4")
    original_v6 = MagicMock(name="original_v6")
    db = GeoDatabase(settings)
    db._ipv4_reader = original_v4
    db._ipv6_reader = original_v6

    async def fail() -> bool:
        raise RuntimeError("network down")

    monkeypatch.setattr(db, "_download_and_open_pair", fail)

    with pytest.raises(GeoDatabaseError):
        await db.refresh()
    assert db._ipv4_reader is original_v4
    assert db._ipv6_reader is original_v6


@pytest.mark.asyncio
async def test_download_honors_304_for_both(settings, monkeypatch, tmp_path):
    ipv4_path = tmp_path / "ipv4.bin"
    ipv6_path = tmp_path / "ipv6.bin"
    ipv4_path.write_bytes(b"v4-existing")
    ipv6_path.write_bytes(b"v6-existing")
    settings.geo_db_ipv4_path = str(ipv4_path)
    settings.geo_db_ipv6_path = str(ipv6_path)

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("if-none-match") in {'"v4"', '"v6"'}:
            return httpx.Response(304)
        code = "DB3LITEBINIPV6" if "DB3LITEBINIPV6" in str(request.url) else "DB3LITEBIN"
        etag = '"v6"' if "IPV6" in code else '"v4"'
        return httpx.Response(
            200,
            content=_zip_with_bin(payload=code.encode()),
            headers={"ETag": etag},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = GeoDatabase(settings, http_client=client)
    monkeypatch.setattr(
        "app.services.database.open_bin",
        lambda path: MagicMock(name="reader"),
    )

    assert await db._download_and_open_pair() is True
    assert db.is_open
    assert await db._download_and_open_pair() is False
    assert any(req.headers.get("if-none-match") for req in seen[2:])
    await db.close()
    await client.aclose()
