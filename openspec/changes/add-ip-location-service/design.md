## Context

Greenfield repo (see proposal.md — Why). Constraints: Python 3.13, FastAPI, pip only (no uv), FastAPI tutorial layout (`app/`), single uvicorn process, env-only config, IPv4 and IPv6. Behavior contracts are in `specs/ip-location-lookup`, `specs/geo-database`, and `specs/india-state-eval`.

Default data file is DB-IP City Lite (~20–30 MB gzip, monthly). The dated URL in the original brief is treated as an instance of `dbip-city-lite-{YYYY-MM}.mmdb.gz`, not a frozen September 2026 pin.

## Goals / Non-Goals

**Goals:**

- One process that can start, download, serve, and hot-swap an MMDB without extra infrastructure.
- A mapping seam (`dbip` / `maxmind`) so a same-schema city MMDB can be swapped via env.
- Manual accuracy tooling that can survive a ~20–25 minute ip-api run.

**Non-Goals:**

- CI, auth, rate limiting of our API, batch lookup, city-level accuracy, multi-worker / gunicorn.
- Paying for ip-api Pro or using other public APIs in this change.
- Committing IP lists, MMDB files, or compare reports.

## Decisions

### 1. Layout and runtime

`app/main.py` (FastAPI + lifespan), `app/config.py` (pydantic-settings), `app/api/routes.py`, `app/services/lookup.py`, `app/services/database.py`, `app/services/profiles.py`. Tests in `tests/`. Manual tools in `scripts/`. Run with one `uvicorn app.main:app` (Docker CMD the same). Port default `8000`.

**Alternative:** src-layout package — rejected; brief asked for a standard FastAPI app tree. **Alternative:** gunicorn + N workers — rejected; mmap hot-swap and start-download are simpler with one process.

### 2. Config surface

| Variable | Default |
|---|---|
| `GEO_DB_URL` | `https://download.db-ip.com/free/dbip-city-lite-{YYYY-MM}.mmdb.gz` |
| `GEO_DB_UPDATE_INTERVAL_SECONDS` | `3600` |
| `GEO_DB_PATH` | `data/geo.mmdb` |
| `GEO_DB_READER_PROFILE` | `dbip` |
| `HOST` / `PORT` | `0.0.0.0` / `8000` |

`{YYYY-MM}` is replaced with the current UTC month. A URL without the placeholder is used as-is (operator-supplied provider). `.env` is loaded for local runs only.

**Alternative:** YAML + env overlay — rejected; operator chose env-only.

### 3. Download, fallback, and swap

Lifespan does: resolve URL(s) → stream to a temp `.gz` → gunzip to a temp `.mmdb` → open with `maxminddb` → atomically replace `GEO_DB_PATH` → publish a new reader. On start, try current month then previous month; if both fail, raise and the process dies. Hourly refresh uses the same sequence; on failure, log and keep the existing reader.

If the remote supports `ETag` / `Last-Modified`, send them and skip rewrite on `304`. Always verify the file opens as MMDB before swapping.

Hold the reader behind a lock or immutable reference so an in-flight lookup finishes on the reader it started with.

**Alternative:** fail closed on hourly errors — rejected; operator chose keep-old at runtime. **Alternative:** require current month only — rejected; 1st-of-month publish lag would brick start.

### 4. Record mapping

Both profiles read `country.iso_code` and `subdivisions[0]` (`iso_code`, `names.en`). `state_iso` is `{country}-{subdivision}` when both exist. Empty subdivision → `null` fields, still `200` if country is present. `ipaddress` validates input; private/reserved or no record → `404`.

Profiles exist so a future vendor-specific field rename does not leak into the route layer. Today `dbip` and `maxmind` city schemas are nearly identical.

### 5. Generator

Open the same local MMDB. Walk networks whose country is `IN`. Sample random hosts (v4 and v6 as the ranges appear). Bucket by MMDB subdivision ISO. Target `1000 / N` per observed state (best effort). Write `ips.txt` (one IP per line) and print coverage to stderr. No committed fixture.

**Alternative:** APNIC delegated ranges — more independent, but the quota label still needs a geo source; local MMDB was chosen. **Alternative:** quota via ip-api — would burn the compare budget during generation.

### 6. Compare script

`scripts/compare_ips.py --input ips.txt --output report.csv --base-url $SERVICE_BASE_URL`. For each IP: `GET {base}/v1/location?ip=...` and `http://ip-api.com/json/{ip}?fields=status,message,countryCode,region,regionName`. Sleep to stay under 45 req/min. Strip `IN-` (or `{CC}-`) from service `state_iso` before comparing to `region`. Names are CSV columns only.

Resume: if `report.csv` exists, load IPs already written and skip them. Append rows as they complete. `429` / transport errors retry with backoff; JSON `status=fail` or empty `region` after a 200 from ip-api is mismatch.

**Alternative:** call the lookup library in-process — rejected; the brief requires going through the service.

### 7. Tests and container

pytest + httpx ASGI client; mock reader and (for script unit tests) mock HTTP. No GitHub Actions. Dockerfile: `python:3.13-slim`, install requirements, `HEALTHCHECK` hits `/healthz`, persist `data/` as a volume (start still re-downloads). Thin `compose.yaml` for local `env_file`. README states DB-IP CC BY 4.0 attribution.

## Risks / Trade-offs

- [Lite MMDB disagrees with ip-api on Indian states] → Expected; report is a measurement, not a CI gate. Verdict is ISO-only to avoid name noise.
- [ip-api free is HTTP-only and 45 req/min] → Documented; ~20–25 min for 1000 rows; resume + throttle.
- [1st-of-month file missing] → Previous-month fallback on start.
- [Hourly download of a monthly file] → `304` / checksum skip; still honors the one-hour interval.
- [IPv6 path sampling in huge prefixes] → Sample a single random host per chosen network, not a dense scan.
- [Thin states / UTs] → Best-effort coverage in the generator summary; do not fail the run.
- [Start always hits the network] → Matches fail-closed start; Docker restarts are slower and need egress.

## Migration Plan

Greenfield: first deploy is the first version. Rollback is revert the image / process. Local data dir is disposable; the next start downloads again. No schema or client compatibility story yet.

## Open Questions

None that affect specs or this approach. Minor names (exact `detail` strings, CSV header spelling) can be fixed at apply time.
