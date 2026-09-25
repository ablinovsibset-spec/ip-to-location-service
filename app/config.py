from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    geo_db_url: str = Field(
        default=(
            "https://github.com/sapics/ip-location-db/releases/download/"
            "latest/geolite2-city-ipv4.mmdb"
        ),
        description="Download URL or monthly template containing {YYYY-MM}.",
    )
    geo_db_update_interval_seconds: int = Field(default=3600, gt=0)
    geo_db_path: str = "data/geo.mmdb"
    geo_db_reader_profile: Literal["geolite2-flat"] = "geolite2-flat"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
