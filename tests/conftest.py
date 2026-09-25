from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.main import create_app
from app.services.database import GeoDatabase


class FakeBinReader:
    def __init__(self, records: dict | None = None) -> None:
        self.records = records or {}

    def get_all(self, ip: str):
        record = self.records.get(ip)
        if record is None:
            return SimpleNamespace(country_short="-", region="-")
        return record

    def close(self) -> None:
        return None


def _record(country: str, region: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        country_short=country,
        region="-" if region is None else region,
    )


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        ip2location_token="test-token",
        geo_db_ipv4_path=str(tmp_path / "ipv4.bin"),
        geo_db_ipv6_path=str(tmp_path / "ipv6.bin"),
        geo_db_update_interval_seconds=86400,
    )


@pytest.fixture
def fake_ipv4_reader() -> FakeBinReader:
    return FakeBinReader(
        {
            "49.36.1.1": _record("IN", "Maharashtra"),
            "8.8.8.8": _record("US"),
            "1.2.3.4": _record("IN"),
        }
    )


@pytest.fixture
def fake_ipv6_reader() -> FakeBinReader:
    return FakeBinReader(
        {
            "2405:201:1::1": _record("IN", "Karnataka"),
        }
    )


@pytest.fixture
def geo_db(settings, fake_ipv4_reader, fake_ipv6_reader) -> GeoDatabase:
    db = GeoDatabase(settings)
    db._ipv4_reader = fake_ipv4_reader
    db._ipv6_reader = fake_ipv6_reader
    return db


@pytest_asyncio.fixture
async def client(settings, geo_db) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=settings, geo_db=geo_db, start_database=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
