import httpx
import pytest
from types import SimpleNamespace

from app.main import create_app
from app.services.database import GeoDatabase
from app.services.lookup import InvalidIpError, LocationNotFoundError, lookup_location
from app.services.profiles import map_ip2location_record


@pytest.mark.asyncio
async def test_ipv4_lookup_success(client):
    response = await client.get("/v1/location", params={"ip": "49.36.1.1"})
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "ip": "49.36.1.1",
        "country": "IN",
        "region": "Maharashtra",
        "found": True,
    }
    assert "city" not in body
    assert "state_iso" not in body
    assert "state_name" not in body


@pytest.mark.asyncio
async def test_ipv6_lookup_success(client):
    response = await client.get("/v1/location", params={"ip": "2405:201:1::1"})
    assert response.status_code == 200
    body = response.json()
    assert body["ip"] == "2405:201:1::1"
    assert body["country"] == "IN"
    assert body["region"] == "Karnataka"
    assert body["found"] is True


@pytest.mark.asyncio
async def test_missing_region_is_200_with_null(client):
    response = await client.get("/v1/location", params={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert response.json() == {
        "ip": "1.2.3.4",
        "country": "IN",
        "region": None,
        "found": True,
    }


@pytest.mark.asyncio
async def test_non_indian_without_region(client):
    response = await client.get("/v1/location", params={"ip": "8.8.8.8"})
    assert response.status_code == 200
    body = response.json()
    assert body["country"] == "US"
    assert body["region"] is None


@pytest.mark.asyncio
async def test_invalid_ip_is_400(client):
    response = await client.get("/v1/location", params={"ip": "not-an-ip"})
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_missing_ip_is_400(client):
    response = await client.get("/v1/location")
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_private_ipv4_is_404(client):
    response = await client.get("/v1/location", params={"ip": "10.0.0.1"})
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_unknown_public_ip_is_404(client):
    response = await client.get("/v1/location", params={"ip": "9.9.9.9"})
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)


@pytest.mark.asyncio
async def test_healthz_200_when_readers_open(client):
    response = await client.get("/healthz")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_healthz_not_200_when_readers_closed(settings):
    geo_db = GeoDatabase(settings)
    app = create_app(settings=settings, geo_db=geo_db, start_database=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/healthz")
    assert response.status_code != 200


def test_lookup_rejects_invalid_and_private(geo_db):
    with pytest.raises(InvalidIpError):
        lookup_location("not-an-ip", geo_db)
    with pytest.raises(LocationNotFoundError):
        lookup_location("192.168.0.1", geo_db)


def test_map_ip2location_dash_sentinels():
    mapped = map_ip2location_record(
        SimpleNamespace(country_short="IN", region="-")
    )
    assert mapped is not None
    assert mapped.country == "IN"
    assert mapped.region is None

    assert map_ip2location_record(SimpleNamespace(country_short="-", region="-")) is None
