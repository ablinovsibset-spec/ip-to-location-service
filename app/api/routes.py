from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from app.services.lookup import InvalidIpError, LocationNotFoundError, lookup_location

router = APIRouter()


class LocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: str
    country: str
    region: str | None
    found: bool


@router.get("/v1/location", response_model=LocationResponse)
async def get_location(
    request: Request,
    ip: str | None = Query(default=None),
) -> LocationResponse:
    if ip is None or ip == "":
        raise HTTPException(status_code=400, detail="Missing ip query parameter")

    geo_db = request.app.state.geo_db
    try:
        result = lookup_location(ip, geo_db)
    except InvalidIpError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return LocationResponse(
        ip=result.ip,
        country=result.country,
        region=result.region,
        found=result.found,
    )


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    if not request.app.state.geo_db.is_open:
        raise HTTPException(status_code=503, detail="Geo database is not open")
    return {"status": "ok"}
