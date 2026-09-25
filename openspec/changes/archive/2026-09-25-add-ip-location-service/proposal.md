## Why

Need a small HTTP service that resolves an IP address to a location, with India as the accuracy focus (state / union territory, not city). The repo is empty; this change defines the first shippable service, its MMDB lifecycle, and a manual accuracy report against a public API.

## What Changes

- Add a FastAPI service that looks up IPv4 and IPv6 addresses in a local MMDB and returns a thin English JSON document (country + state).
- Download the configured MMDB on process start (must succeed) and refresh it on a schedule (default hourly); provider URL, interval, file path, and reader profile are environment-configurable.
- Add unit tests (mocked reader / HTTP) that run locally; no CI in this change.
- Add two manual scripts: generate ~1000 random Indian IPs with a per-state quota, and compare the service against ip-api.com, writing a resumable CSV report judged on ISO state codes only.
- Add a Dockerfile and a single-process uvicorn runtime. DB-IP attribution lives in the README only.

## Capabilities

### New Capabilities

- `ip-location-lookup`: REST lookup (`GET /v1/location`), validation / not-found behavior, `/healthz`.
- `geo-database`: MMDB download, monthly URL template with previous-month fallback, scheduled refresh, provider profiles, start vs runtime failure rules.
- `india-state-eval`: generate the IP list from local MMDB ranges; compare 1000 addresses to ip-api.com; CSV report with resume.

### Modified Capabilities

- None. `openspec/specs/` is empty; this is a greenfield service.

## Impact

- New Python 3.14 application under `app/` (FastAPI + MMDB reader), `tests/`, `scripts/`, `requirements.txt`, `.env.example`, Dockerfile, README.
- External systems: DB-IP City Lite (or a configured MMDB URL) on start and hourly; ip-api.com only from the manual compare script (rate-limited).
- No existing APIs or packages to break.
- License: DB-IP City Lite is CC BY 4.0 — attribution in README.
