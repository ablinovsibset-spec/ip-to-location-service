from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ip2location_token: str = Field(
        default="",
        description="Download token from the IP2Location account portal.",
    )
    geo_db_ipv4_code: str = Field(
        default="DB3LITEBIN",
        description="IP2Location download package code for the IPv4 LITE DB3 BIN.",
    )
    geo_db_ipv6_code: str = Field(
        default="DB3LITEBINIPV6",
        description="IP2Location download package code for the IPv6 LITE DB3 BIN.",
    )
    geo_db_ipv4_path: str = "data/IP2LOCATION-LITE-DB3.BIN"
    geo_db_ipv6_path: str = "data/IP2LOCATION-LITE-DB3.IPV6.BIN"
    geo_db_update_interval_seconds: int = Field(default=86400, gt=0)
    geo_db_download_base_url: str = "https://www.ip2location.com/download"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
