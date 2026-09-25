#!/usr/bin/env python3
"""Compare the running service against ip-api.com for a list of IPs.

Manual operator tool. Do not commit generated IP lists or CSV reports.
Queries the HTTP service (not the lookup library in-process).
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx

IPAPI_URL = "http://ip-api.com/json/{ip}?fields=status,message,countryCode,region,regionName"
MAX_IPAPI_PER_MINUTE = 45
MIN_IPAPI_INTERVAL = 60.0 / MAX_IPAPI_PER_MINUTE
CSV_FIELDS = [
    "ip",
    "service_state_iso",
    "service_state_name",
    "ipapi_region",
    "ipapi_region_name",
    "verdict",
]


def strip_country_prefix(state_iso: str | None) -> str | None:
    if not state_iso:
        return None
    if "-" in state_iso:
        return state_iso.split("-", 1)[1]
    return state_iso


def iso_verdict(
    service_state_iso: str | None,
    ipapi_status: str | None,
    ipapi_region: str | None,
) -> str:
    """Compare ISO subdivision codes only. Names never affect the verdict."""
    if ipapi_status == "fail" or not ipapi_region:
        return "mismatch"
    service_code = strip_country_prefix(service_state_iso)
    if service_code and service_code.casefold() == ipapi_region.casefold():
        return "match"
    return "mismatch"


def load_done_ips(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    done: set[str] = set()
    with output_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ip = (row.get("ip") or "").strip()
            if ip:
                done.add(ip)
    return done


def read_input_ips(input_path: Path) -> list[str]:
    ips: list[str] = []
    seen: set[str] = set()
    for raw in input_path.read_text().splitlines():
        ip = raw.strip()
        if not ip or ip.startswith("#") or ip in seen:
            continue
        seen.add(ip)
        ips.append(ip)
    return ips


def query_service(client: httpx.Client, base_url: str, ip: str) -> dict:
    url = base_url.rstrip("/") + "/v1/location"
    response = client.get(url, params={"ip": ip}, timeout=30.0)
    if response.status_code != 200:
        return {"state_iso": None, "state_name": None}
    body = response.json()
    return {
        "state_iso": body.get("state_iso"),
        "state_name": body.get("state_name"),
    }


def query_ipapi(client: httpx.Client, ip: str, retries: int = 5) -> dict:
    url = IPAPI_URL.format(ip=ip)
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.get(url, timeout=30.0)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                time.sleep(wait)
                delay *= 2
                continue
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code != 429:
                if exc.response.status_code < 500:
                    raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"ip-api request failed after retries: {ip}") from last_error


def compare_one(client: httpx.Client, base_url: str, ip: str) -> dict[str, str | None]:
    service = query_service(client, base_url, ip)
    ipapi = query_ipapi(client, ip)
    status = ipapi.get("status")
    region = ipapi.get("region") or None
    return {
        "ip": ip,
        "service_state_iso": service.get("state_iso"),
        "service_state_name": service.get("state_name"),
        "ipapi_region": region,
        "ipapi_region_name": ipapi.get("regionName"),
        "verdict": iso_verdict(service.get("state_iso"), status, region),
    }


def run(input_path: Path, output_path: Path, base_url: str) -> int:
    ips = read_input_ips(input_path)
    done = load_done_ips(output_path)
    remaining = [ip for ip in ips if ip not in done]
    new_file = not output_path.exists()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
            handle.flush()
        with httpx.Client() as client:
            for ip in remaining:
                started = time.monotonic()
                row = compare_one(client, base_url, ip)
                writer.writerow(row)
                handle.flush()
                elapsed = time.monotonic() - started
                sleep_for = MIN_IPAPI_INTERVAL - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual compare of the location service vs ip-api.com (ISO state only)."
    )
    parser.add_argument("--input", required=True, type=Path, help="One IP per line")
    parser.add_argument("--output", required=True, type=Path, help="CSV report path")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Running service base URL, e.g. http://127.0.0.1:8000",
    )
    args = parser.parse_args(argv)
    return run(args.input, args.output, args.base_url)


if __name__ == "__main__":
    sys.exit(main())
