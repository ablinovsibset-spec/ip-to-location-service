from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MappedLocation:
    country: str
    state_iso: str | None
    state_name: str | None


class ReaderProfile(Protocol):
    def map_record(self, record: Any) -> MappedLocation | None: ...


def map_geolite2_flat(record: Any) -> MappedLocation | None:
    """Map a sapics/ip-location-db GeoLite2 flat city record."""
    if not isinstance(record, dict):
        return None
    country_code = record.get("country_code")
    if not country_code:
        return None

    state1 = record.get("state1")
    state_name = str(state1) if state1 else None

    return MappedLocation(
        country=str(country_code),
        state_iso=None,
        state_name=state_name,
    )


class Geolite2FlatProfile:
    def map_record(self, record: Any) -> MappedLocation | None:
        return map_geolite2_flat(record)


PROFILES: dict[str, ReaderProfile] = {
    "geolite2-flat": Geolite2FlatProfile(),
}


def get_profile(name: str) -> ReaderProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown reader profile: {name}") from exc
