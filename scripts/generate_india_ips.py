#!/usr/bin/env python3
"""Sample ~1000 random Indian IPs from the local MMDB with a per-state quota.

Manual operator tool. Do not commit the generated IP list.
Coverage is printed to stderr; the output file is one IP per line.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

import maxminddb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.profiles import get_profile

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def random_host(network: Network) -> str:
    n = network.num_addresses
    if network.version == 4 and network.prefixlen <= 30:
        offset = random.randint(1, n - 2)
    else:
        offset = random.randint(0, n - 1)
    return str(network.network_address + offset)


def collect_india_networks(
    reader: maxminddb.Reader, profile_name: str
) -> dict[str, list[Network]]:
    profile = get_profile(profile_name)
    by_state: dict[str, list[Network]] = defaultdict(list)
    for network, record in reader:
        mapped = profile.map_record(record)
        if mapped is None or mapped.country != "IN":
            continue
        label = mapped.state_iso or "UNKNOWN"
        by_state[label].append(network)
    return by_state


def sample_by_quota(
    by_state: dict[str, list[Network]],
    target: int,
) -> tuple[list[str], dict[str, tuple[int, int]]]:
    states = sorted(by_state)
    if not states:
        return [], {}
    base, remainder = divmod(target, len(states))
    quotas = {
        state: base + (1 if index < remainder else 0)
        for index, state in enumerate(states)
    }

    selected: list[str] = []
    coverage: dict[str, tuple[int, int]] = {}
    for state in states:
        networks = list(by_state[state])
        random.shuffle(networks)
        quota = quotas[state]
        seen: set[str] = set()
        picked: list[str] = []
        if not networks:
            coverage[state] = (0, quota)
            continue
        attempts = 0
        max_attempts = max(quota * 20, len(networks) * 3, 1)
        while len(picked) < quota and attempts < max_attempts:
            network = networks[attempts % len(networks)]
            ip = random_host(network)
            if ip not in seen:
                seen.add(ip)
                picked.append(ip)
            attempts += 1
        selected.extend(picked)
        coverage[state] = (len(picked), quota)
    random.shuffle(selected)
    return selected, coverage


def print_coverage(coverage: dict[str, tuple[int, int]], total: int) -> None:
    print("India IP coverage (sampled / quota):", file=sys.stderr)
    for state in sorted(coverage):
        got, quota = coverage[state]
        print(f"  {state}: {got}/{quota}", file=sys.stderr)
    print(f"Total: {total}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual generator of random Indian IPs from the local MMDB."
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("GEO_DB_PATH", "data/geo.mmdb"),
        help="Path to the local MMDB (default: GEO_DB_PATH or data/geo.mmdb)",
    )
    parser.add_argument("--output", default="ips.txt", help="One-column IP output file")
    parser.add_argument("--count", type=int, default=1000, help="Target unique IPs")
    parser.add_argument(
        "--profile",
        default=os.environ.get("GEO_DB_READER_PROFILE", "dbip"),
        choices=("dbip", "maxmind"),
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"MMDB not found: {db_path}", file=sys.stderr)
        return 1

    with maxminddb.open_database(db_path) as reader:
        by_state = collect_india_networks(reader, args.profile)
        selected, coverage = sample_by_quota(by_state, args.count)

    output = Path(args.output)
    output.write_text("".join(f"{ip}\n" for ip in selected))
    print_coverage(coverage, len(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
