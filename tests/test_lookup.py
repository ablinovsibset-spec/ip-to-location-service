import httpx
import pytest

from app.main import create_app
from app.services.database import GeoDatabase
from app.services.lookup import InvalidIpError, LocationNotFoundError, lookup_location
from app.services.profiles import get_profile
from tests.conftest import FakeReader


@pytest.mark.asyncio
async def test_ipv4_lookup_success(client):
    response = await client.get("/v1/location", params={"ip": "49.36.1.1"})
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "ip": "49.36.1.1",
        "country": "IN",
        "state_iso": "IN-MH",
        "state_name": "Maharashtra",
        "found": True,
    }
    assert "city" not in body
    assert "latitude" not in body
    assert "longitude" not in body


@pytest.mark.asyncio
async def test_ipv6_lookup_success(client):
    response = await client.get("/v1/location", params={"ip": "2405:201:1::1"})
    assert response.status_code == 200
    body = response.json()
    assert body["ip"] == "2405:201:1::1"
    assert body["country"] == "IN"
    assert body["state_iso"] == "IN-KA"
    assert body["state_name"] == "Karnataka"
    assert body["found"] is True


@pytest.mark.asyncio
async def test_missing_subdivision_is_200_with_null_state(client):
    response = await client.get("/v1/location", params={"ip": "1.2.3.4"})
    assert response.status_code == 200
    assert response.json() == {
        "ip": "1.2.3.4",
        "country": "IN",
        "state_iso": None,
        "state_name": None,
        "found": True,
    }


@pytest.mark.asyncio
async def test_non_indian_without_subdivision(client):
    response = await client.get("/v1/location", params={"ip": "8.8.8.8"})
    assert response.status_code == 200
    body = response.json()
    assert body["country"] == "US"
    assert body["state_iso"] is None
    assert body["state_name"] is None


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
async def test_healthz_200_when_reader_open(client):
    response = await client.get("/healthz")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_healthz_not_200_when_reader_closed(settings):
    geo_db = GeoDatabase(settings)
    app = create_app(settings=settings, geo_db=geo_db, start_database=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/healthz")
    assert response.status_code != 200


def test_lookup_rejects_invalid_and_private(geo_db):
    profile = get_profile("dbip")
    with pytest.raises(InvalidIpError):
        lookup_location("not-an-ip", geo_db, profile)
    with pytest.raises(LocationNotFoundError):
        lookup_location("192.168.0.1", geo_db, profile)


def test_maxmind_profile_maps_same_city_schema():
    profile = get_profile("maxmind")
    mapped = profile.map_record(
        {
            "country": {"iso_code": "IN"},
            "subdivisions": [{"iso_code": "DL", "names": {"en": "Delhi"}}],
        }
    )
    assert mapped is not None
    assert mapped.country == "IN"
    assert mapped.state_iso == "IN-DL"
    assert mapped.state_name == "Delhi"


def test_fake_reader_is_used_not_live_mmdb():
    reader = FakeReader({"1.1.1.1": {"country": {"iso_code": "AU"}}})
    assert reader.get("1.1.1.1")["country"]["iso_code"] == "AU"
