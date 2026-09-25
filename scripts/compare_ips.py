#!/usr/bin/env python3
"""Compare the running service against ip-api.com for a list of IPs.

Manual operator tool. Do not commit generated IP lists or CSV reports.
Queries the HTTP service (not the lookup library in-process).
Writes only mismatches: expected (ip-api) vs service region names.
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
    "expected_region",
    "service_region",
    "note",
]

# Alternate English labels for the same Indian state / UT (ip-api vs IP2Location).
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "delhi",
            "national capital territory of delhi",
            "nct of delhi",
            "nct delhi",
        }
    ),
    frozenset(
        {
            "puducherry",
            "pondicherry",
            "union territory of puducherry",
            "ut of puducherry",
        }
    ),
    frozenset(
        {
            "andaman and nicobar",
            "andaman and nicobar islands",
            "andaman & nicobar",
            "andaman & nicobar islands",
        }
    ),
    frozenset({"odisha", "orissa"}),
)


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized.casefold() or None


def _synonym_canonical(normalized: str) -> str:
    for group in _SYNONYM_GROUPS:
        if normalized in group:
            return sorted(group)[0]
    return normalized


def are_synonyms(left: str | None, right: str | None) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b or a == b:
        return False
    return _synonym_canonical(a) == _synonym_canonical(b)


def mismatch_note(service_region: str | None, expected_region: str | None) -> str:
    return "synonym" if are_synonyms(service_region, expected_region) else ""


def name_verdict(
    service_region: str | None,
    ipapi_status: str | None,
    ipapi_region_name: str | None,
) -> str:
    """Compare English region names only."""
    if ipapi_status == "fail" or not normalize_name(ipapi_region_name):
        return "mismatch"
    service = normalize_name(service_region)
    reference = normalize_name(ipapi_region_name)
    if service and reference and service == reference:
        return "match"
    return "mismatch"


def done_path_for(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".done")


def load_done_ips(output_path: Path) -> set[str]:
    path = done_path_for(output_path)
    if not path.exists():
        return set()
    done: set[str] = set()
    for raw in path.read_text().splitlines():
        ip = raw.strip()
        if ip:
            done.add(ip)
    return done


def mark_done(done_file, ip: str) -> None:
    done_file.write(f"{ip}\n")
    done_file.flush()


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
        return {"region": None}
    body = response.json()
    return {"region": body.get("region")}


def query_ipapi(client: httpx.Client, ip: str, retries: int = 5) -> dict:
    url = IPAPI_URL.format(ip=ip)
    delay = 2.0
    last_error: Exception | None = None
    for _attempt in range(retries):
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
    region_name = ipapi.get("regionName") or None
    service_region = service.get("region")
    return {
        "ip": ip,
        "expected_region": region_name,
        "service_region": service_region,
        "verdict": name_verdict(service_region, status, region_name),
    }


def run(input_path: Path, output_path: Path, base_url: str) -> int:
    ips = read_input_ips(input_path)
    done = load_done_ips(output_path)
    remaining = [ip for ip in ips if ip not in done]
    new_file = not output_path.exists()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path = done_path_for(output_path)

    with (
        output_path.open("a", newline="") as handle,
        progress_path.open("a") as done_file,
    ):
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
            extrasaction="ignore",
            lineterminator="\n",
        )
        if new_file:
            writer.writeheader()
            handle.flush()
        with httpx.Client() as client:
            for ip in remaining:
                started = time.monotonic()
                row = compare_one(client, base_url, ip)
                if row["verdict"] == "mismatch":
                    writer.writerow(
                        {
                            "ip": row["ip"],
                            "expected_region": row["expected_region"] or "",
                            "service_region": row["service_region"] or "",
                            "note": mismatch_note(
                                row["service_region"],
                                row["expected_region"],
                            ),
                        }
                    )
                    handle.flush()
                mark_done(done_file, ip)
                elapsed = time.monotonic() - started
                sleep_for = MIN_IPAPI_INTERVAL - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual compare of the location service vs ip-api.com "
            "(mismatch-only report: expected vs service region name)."
        )
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
