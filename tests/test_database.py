import gzip
from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.database import (
    GeoDatabase,
    GeoDatabaseError,
    previous_utc_month,
    resolve_url,
    start_urls,
)


def test_resolve_url_replaces_utc_month():
    when = datetime(2026, 9, 15, tzinfo=UTC)
    url = resolve_url(
        "https://download.db-ip.com/free/dbip-city-lite-{YYYY-MM}.mmdb.gz",
        when,
    )
    assert url.endswith("dbip-city-lite-2026-09.mmdb.gz")


def test_resolve_url_literal_unchanged():
    literal = "https://example.com/custom.mmdb.gz"
    assert resolve_url(literal) == literal


def test_start_urls_try_current_then_previous_month():
    when = datetime(2026, 1, 5, tzinfo=UTC)
    urls = start_urls("https://example.com/db-{YYYY-MM}.mmdb.gz", when)
    assert urls == [
        "https://example.com/db-2026-01.mmdb.gz",
        "https://example.com/db-2025-12.mmdb.gz",
    ]


def test_previous_utc_month_rolls_year():
    when = datetime(2026, 1, 31, tzinfo=UTC)
    assert previous_utc_month(when).strftime("%Y-%m") == "2025-12"


def _gzip_body(payload: bytes = b"mmdb-bytes") -> bytes:
    return gzip.compress(payload)


def _handler_factory(routes: dict[str, httpx.Response], seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = str(request.url)
        for url, response in routes.items():
            if url in key:
                return response
        return httpx.Response(404, text="missing")

    return handler


@pytest.mark.asyncio
async def test_start_uses_previous_month_when_current_missing(settings, monkeypatch):
    current = "dbip-city-lite-2026-09.mmdb.gz"
    previous = "dbip-city-lite-2026-08.mmdb.gz"
    seen: list[httpx.Request] = []
    routes = {
        current: httpx.Response(404, text="not found"),
        previous: httpx.Response(
            200,
            content=_gzip_body(),
            headers={"ETag": '"aug"', "Content-Type": "application/gzip"},
        ),
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler_factory(routes, seen)))
    db = GeoDatabase(settings, http_client=client)
    monkeypatch.setattr(
        "app.services.database.maxminddb.open_database",
        lambda path: MagicMock(name="reader"),
    )
    monkeypatch.setattr(
        "app.services.database.start_urls",
        lambda template, when=None: start_urls(template, datetime(2026, 9, 25, tzinfo=UTC)),
    )

    await db.start()
    assert db.is_open
    urls = [str(req.url) for req in seen]
    assert any(current in url for url in urls)
    assert any(previous in url for url in urls)
    await db.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_start_fails_when_neither_month_downloads(settings, monkeypatch):
    seen: list[httpx.Request] = []
    routes = {}
    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler_factory(routes, seen)))
    db = GeoDatabase(settings, http_client=client)
    monkeypatch.setattr(
        "app.services.database.start_urls",
        lambda template, when=None: [
            "https://example.com/now.mmdb.gz",
            "https://example.com/prev.mmdb.gz",
        ],
    )
    with pytest.raises(GeoDatabaseError):
        await db.start()
    assert not db.is_open
    await client.aclose()


@pytest.mark.asyncio
async def test_refresh_keeps_old_reader_on_failure(settings, monkeypatch):
    original = MagicMock(name="original")
    db = GeoDatabase(settings)
    db._reader = original

    async def fail(_url: str) -> bool:
        raise RuntimeError("network down")

    monkeypatch.setattr(db, "_download_and_open", fail)
    monkeypatch.setattr(
        "app.services.database.start_urls",
        lambda template, when=None: ["https://example.com/now.mmdb.gz"],
    )

    with pytest.raises(GeoDatabaseError):
        await db.refresh()
    assert db.get_reader() is original


@pytest.mark.asyncio
async def test_download_honors_304_and_validators(settings, monkeypatch, tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("if-none-match") == '"abc"':
            return httpx.Response(304)
        return httpx.Response(
            200,
            content=_gzip_body(),
            headers={"ETag": '"abc"', "Last-Modified": "Wed, 01 Sep 2026 00:00:00 GMT"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = GeoDatabase(settings, http_client=client)
    monkeypatch.setattr(
        "app.services.database.maxminddb.open_database",
        lambda path: MagicMock(name="reader"),
    )

    assert await db._download_and_open("https://example.com/db.mmdb.gz") is True
    first = db.get_reader()
    assert await db._download_and_open("https://example.com/db.mmdb.gz") is False
    assert db.get_reader() is first
    assert seen[1].headers.get("if-none-match") == '"abc"'
    await db.close()
    await client.aclose()
