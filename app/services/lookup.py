import ipaddress
from dataclasses import dataclass

from app.services.database import GeoDatabase
from app.services.profiles import MappedLocation, ReaderProfile


class InvalidIpError(ValueError):
    pass


class LocationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class LocationResult:
    ip: str
    country: str
    state_iso: str | None
    state_name: str | None
    found: bool = True


def parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(value)
    except ValueError as exc:
        raise InvalidIpError("Invalid IP address") from exc


def lookup_location(
    ip: str,
    geo_db: GeoDatabase,
    profile: ReaderProfile,
) -> LocationResult:
    addr = parse_ip(ip)
    if isinstance(addr, ipaddress.IPv6Address):
        raise InvalidIpError("IPv6 is not supported")
    if not addr.is_global:
        raise LocationNotFoundError("Location not found")

    record = geo_db.lookup_record(str(addr))
    mapped: MappedLocation | None = profile.map_record(record)
    if mapped is None:
        raise LocationNotFoundError("Location not found")

    return LocationResult(
        ip=ip,
        country=mapped.country,
        state_iso=mapped.state_iso,
        state_name=mapped.state_name,
        found=True,
    )
