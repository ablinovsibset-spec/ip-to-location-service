## 1. Project skeleton

- [x] 1.1 Add `requirements.txt` for Python 3.14 (fastapi, uvicorn, pydantic-settings, maxminddb, httpx, pytest, pytest-asyncio) and `.env.example` with the env vars from design.md
- [x] 1.2 Create `app/` tree (`main.py`, `config.py`, `api/routes.py`, `services/`) plus `tests/` and `scripts/`; ignore `data/`, `.env`, `*.mmdb`, generated IP lists and CSV reports

## 2. Database lifecycle

- [x] 2.1 Implement env config: URL/template, interval (default 3600), path, reader profile (`dbip` / `maxmind`)
- [x] 2.2 Implement download: resolve `{YYYY-MM}` in UTC, stream gzip, extract, open as MMDB, atomic replace at `GEO_DB_PATH`; honor 304 / validators when present
- [x] 2.3 On start, try current month then previous month; exit the process if neither download+open succeeds
- [x] 2.4 After start, refresh on the configured interval; on failure log and keep the current reader; swap readers without dropping in-flight lookups
- [x] 2.5 Implement `dbip` and `maxmind` profiles that map country ISO + first subdivision to `country`, `state_iso` (`CC-SUB`), `state_name`

## 3. Lookup API

- [x] 3.1 Add FastAPI lifespan that runs the start-download before serving and starts the refresh task
- [x] 3.2 Implement `GET /v1/location?ip=`: validate IPv4/IPv6, 400 on bad/missing input, 404 on private/reserved/no record, 200 thin body (`ip`, `country`, `state_iso`, `state_name`, `found`)
- [x] 3.3 Return 200 with `state_*` null when a record has a country but no subdivision; do not include city or coordinates
- [x] 3.4 Implement `GET /healthz` → 200 only when an MMDB reader is open

## 4. Unit tests

- [x] 4.1 Test lookup success, missing subdivision, invalid IP (400), private/unknown (404), IPv4 and IPv6 with a mocked reader
- [x] 4.2 Test URL month resolution, previous-month fallback, start failure, and refresh-keeps-old with mocked HTTP
- [x] 4.3 Test name verdict helper (case/whitespace normalize, ISO ignored, ip-api fail → mismatch) without calling the network

## 5. Evaluation scripts

- [x] 5.1 Add `scripts/generate_india_ips.py` that samples ~1000 random IN hosts from the local MMDB with per-state quota (best effort) and writes a one-column text file plus coverage to stderr
- [x] 5.2 Add `scripts/compare_ips.py` that reads that file, queries the running service and ip-api.com (≤45 req/min, retries on 429/transport), writes incremental CSV, and resumes from an existing output
- [x] 5.3 Document that both scripts are manual and that IP lists / reports are not committed

## 6. Container and README

- [x] 6.1 Add Dockerfile (`python:3.14-slim`, single uvicorn, `HEALTHCHECK` on `/healthz`) and a thin `compose.yaml` with `env_file`
- [x] 6.2 Write README: how to run locally, env vars, Docker, script usage, and DB-IP CC BY 4.0 attribution
