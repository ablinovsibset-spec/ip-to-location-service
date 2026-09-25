from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MappedLocation:
    country: str
    state_iso: str | None
    state_name: str | None


class ReaderProfile(Protocol):
    def map_record(self, record: Any) -> MappedLocation | None: ...


def _first_subdivision(record: dict[str, Any]) -> dict[str, Any] | None:
    subdivisions = record.get("subdivisions") or []
    if not subdivisions:
        return None
    first = subdivisions[0]
    return first if isinstance(first, dict) else None


def map_city_schema(record: Any) -> MappedLocation | None:
    """Map a MaxMind/DB-IP city-schema record to country + first subdivision."""
    if not isinstance(record, dict):
        return None
    country = record.get("country") or {}
    if not isinstance(country, dict):
        return None
    country_iso = country.get("iso_code")
    if not country_iso:
        return None

    state_iso = None
    state_name = None
    subdivision = _first_subdivision(record)
    if subdivision:
        sub_iso = subdivision.get("iso_code")
        names = subdivision.get("names") or {}
        if sub_iso:
            state_iso = sub_iso if "-" in str(sub_iso) else f"{country_iso}-{sub_iso}"
        if isinstance(names, dict):
            state_name = names.get("en")

    return MappedLocation(
        country=str(country_iso),
        state_iso=state_iso,
        state_name=state_name,
    )


class DbipProfile:
    def map_record(self, record: Any) -> MappedLocation | None:
        return map_city_schema(record)


class MaxmindProfile:
    def map_record(self, record: Any) -> MappedLocation | None:
        return map_city_schema(record)


PROFILES: dict[str, ReaderProfile] = {
    "dbip": DbipProfile(),
    "maxmind": MaxmindProfile(),
}


def get_profile(name: str) -> ReaderProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown reader profile: {name}") from exc
