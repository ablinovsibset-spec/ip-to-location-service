#!/usr/bin/env python3
"""Sample ~1000 random Indian IPs via local IP2Location BINs (soft region quota).

Manual operator tool. Do not commit the generated IP list.
Samples public IPv4 and IPv6 space, looks up each address in the local BINs,
and aims for a soft per-region quota. Coverage is printed to stderr.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import IP2Location

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.profiles import map_ip2location_record


def random_public_ipv4() -> str:
    while True:
        candidate = ipaddress.IPv4Address(random.getrandbits(32))
        if candidate.is_global:
            return str(candidate)


def random_public_ipv6() -> str:
    # Global unicast 2000::/3
    while True:
        bits = (0b001 << 125) | random.getrandbits(125)
        candidate = ipaddress.IPv6Address(bits)
        if candidate.is_global:
            return str(candidate)


def random_public_ip(*, prefer_v6: bool) -> str:
    return random_public_ipv6() if prefer_v6 else random_public_ipv4()


def discover_regions(
    ipv4_db: IP2Location.IP2Location,
    ipv6_db: IP2Location.IP2Location,
    *,
    max_attempts: int,
    plateau: int,
) -> set[str]:
    """Discover IN region labels by random sampling until plateau."""
    regions: set[str] = set()
    stagnant = 0
    for attempt in range(max_attempts):
        prefer_v6 = attempt % 2 == 1
        ip = random_public_ip(prefer_v6=prefer_v6)
        reader = ipv6_db if prefer_v6 else ipv4_db
        mapped = map_ip2location_record(reader.get_all(ip))
        if mapped is None or mapped.country != "IN":
            continue
        label = mapped.region or "UNKNOWN"
        if label in regions:
            stagnant += 1
            if stagnant >= plateau and regions:
                break
            continue
        regions.add(label)
        stagnant = 0
    return regions


def sample_soft_quota(
    ipv4_db: IP2Location.IP2Location,
    ipv6_db: IP2Location.IP2Location,
    regions: set[str],
    target: int,
    *,
    max_attempts_per_region: int,
) -> tuple[list[str], dict[str, tuple[int, int]]]:
    labels = sorted(regions) or ["UNKNOWN"]
    base, remainder = divmod(target, len(labels))
    quotas = {
        label: base + (1 if index < remainder else 0)
        for index, label in enumerate(labels)
    }
    buckets: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()

    for label in labels:
        quota = quotas[label]
        attempts = 0
        while len(buckets[label]) < quota and attempts < max_attempts_per_region:
            attempts += 1
            prefer_v6 = attempts % 2 == 1
            ip = random_public_ip(prefer_v6=prefer_v6)
            if ip in seen:
                continue
            reader = ipv6_db if prefer_v6 else ipv4_db
            mapped = map_ip2location_record(reader.get_all(ip))
            if mapped is None or mapped.country != "IN":
                continue
            found = mapped.region or "UNKNOWN"
            if found != label:
                # Still useful: bank into the matching bucket if under quota.
                if found in quotas and len(buckets[found]) < quotas[found]:
                    seen.add(ip)
                    buckets[found].append(ip)
                continue
            seen.add(ip)
            buckets[label].append(ip)

    selected: list[str] = []
    coverage: dict[str, tuple[int, int]] = {}
    for label in labels:
        picked = buckets[label]
        selected.extend(picked)
        coverage[label] = (len(picked), quotas[label])

    # Top up to target with any leftover IN hits if soft quota undershot.
    topup_attempts = 0
    max_topup = max(target * 20, 1000)
    while len(selected) < target and topup_attempts < max_topup:
        topup_attempts += 1
        prefer_v6 = topup_attempts % 2 == 1
        ip = random_public_ip(prefer_v6=prefer_v6)
        if ip in seen:
            continue
        reader = ipv6_db if prefer_v6 else ipv4_db
        mapped = map_ip2location_record(reader.get_all(ip))
        if mapped is None or mapped.country != "IN":
            continue
        seen.add(ip)
        selected.append(ip)
        label = mapped.region or "UNKNOWN"
        got, quota = coverage.get(label, (0, 0))
        coverage[label] = (got + 1, quota)

    random.shuffle(selected)
    return selected[:target], coverage


def print_coverage(coverage: dict[str, tuple[int, int]], total: int) -> None:
    print("India IP coverage (sampled / quota):", file=sys.stderr)
    for region in sorted(coverage):
        got, quota = coverage[region]
        print(f"  {region}: {got}/{quota}", file=sys.stderr)
    print(f"Total: {total}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual generator of random Indian IPs by sampling public "
            "IPv4/IPv6 space against local IP2Location LITE DB3 BINs."
        )
    )
    parser.add_argument(
        "--ipv4-db",
        default=os.environ.get("GEO_DB_IPV4_PATH", "data/IP2LOCATION-LITE-DB3.BIN"),
        help="Path to the IPv4 BIN",
    )
    parser.add_argument(
        "--ipv6-db",
        default=os.environ.get("GEO_DB_IPV6_PATH", "data/IP2LOCATION-LITE-DB3.IPV6.BIN"),
        help="Path to the IPv6 BIN",
    )
    parser.add_argument("--output", default="ips.txt", help="One-column IP output file")
    parser.add_argument("--count", type=int, default=1000, help="Target unique IPs")
    parser.add_argument(
        "--max-attempts-per-region",
        type=int,
        default=50_000,
        help="Soft quota attempt cap per discovered region",
    )
    parser.add_argument(
        "--discover-attempts",
        type=int,
        default=100_000,
        help="Max random lookups while discovering IN regions",
    )
    args = parser.parse_args(argv)

    ipv4_path = Path(args.ipv4_db)
    ipv6_path = Path(args.ipv6_db)
    for path in (ipv4_path, ipv6_path):
        if not path.exists():
            print(f"BIN not found: {path}", file=sys.stderr)
            return 1

    started = time.monotonic()
    ipv4_db = IP2Location.IP2Location(str(ipv4_path))
    ipv6_db = IP2Location.IP2Location(str(ipv6_path))
    try:
        regions = discover_regions(
            ipv4_db,
            ipv6_db,
            max_attempts=args.discover_attempts,
            plateau=2_000,
        )
        if not regions:
            print("No Indian regions discovered; aborting.", file=sys.stderr)
            return 1
        selected, coverage = sample_soft_quota(
            ipv4_db,
            ipv6_db,
            regions,
            args.count,
            max_attempts_per_region=args.max_attempts_per_region,
        )
    finally:
        ipv4_db.close()
        ipv6_db.close()

    output = Path(args.output)
    output.write_text("".join(f"{ip}\n" for ip in selected))
    print_coverage(coverage, len(selected))
    print(f"Elapsed: {time.monotonic() - started:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
