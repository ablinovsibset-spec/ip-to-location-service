from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MappedLocation:
    country: str
    region: str | None


def _field(record: Any, name: str) -> str | None:
    value = getattr(record, name, None)
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    return text


def map_ip2location_record(record: Any) -> MappedLocation | None:
    """Map an IP2Location BIN record to country + region name."""
    if record is None:
        return None
    country = _field(record, "country_short")
    if not country:
        return None
    return MappedLocation(country=country, region=_field(record, "region"))
