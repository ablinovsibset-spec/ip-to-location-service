from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.main import create_app
from app.services.database import GeoDatabase


class FakeReader:
    def __init__(self, records: dict | None = None) -> None:
        self.records = records or {}

    def get(self, ip: str):
        return self.records.get(ip)

    def close(self) -> None:
        return None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        geo_db_path=str(tmp_path / "geo.mmdb"),
        geo_db_update_interval_seconds=3600,
        geo_db_reader_profile="dbip",
    )


@pytest.fixture
def fake_reader() -> FakeReader:
    return FakeReader(
        {
            "49.36.1.1": {
                "country": {"iso_code": "IN"},
                "subdivisions": [{"iso_code": "MH", "names": {"en": "Maharashtra"}}],
                "city": {"names": {"en": "Mumbai"}},
                "location": {"latitude": 19.07, "longitude": 72.87},
            },
            "2405:201:1::1": {
                "country": {"iso_code": "IN"},
                "subdivisions": [{"iso_code": "KA", "names": {"en": "Karnataka"}}],
            },
            "8.8.8.8": {
                "country": {"iso_code": "US"},
            },
            "1.2.3.4": {
                "country": {"iso_code": "IN"},
            },
        }
    )


@pytest.fixture
def geo_db(settings, fake_reader) -> GeoDatabase:
    db = GeoDatabase(settings)
    db._reader = fake_reader
    return db


@pytest_asyncio.fixture
async def client(settings, geo_db) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=settings, geo_db=geo_db, start_database=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
