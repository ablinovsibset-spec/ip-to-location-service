# IP to Location Service

Small FastAPI service that maps an IPv4 or IPv6 address to country and administrative state using a local MMDB file. India (state / union territory) is the accuracy focus. The default database is [DB-IP City Lite](https://db-ip.com/).

This product includes IP to City Lite data from [DB-IP](https://db-ip.com/) — IP Geolocation by DB-IP, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

## Requirements

- Python 3.14
- pip (do not use uv)

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On start the process **must** download and open an MMDB. If the current UTC month file is missing it tries the previous month. If both fail the process exits, even when an older file is already on disk.

```bash
curl 'http://127.0.0.1:8000/v1/location?ip=49.36.1.1'
curl 'http://127.0.0.1:8000/healthz'
```

A successful lookup is a thin JSON document:

```json
{
  "ip": "49.36.1.1",
  "country": "IN",
  "state_iso": "IN-MH",
  "state_name": "Maharashtra",
  "found": true
}
```

`GET /healthz` returns 200 only when an MMDB reader is open.

## Environment

| Variable | Default |
|---|---|
| `GEO_DB_URL` | `https://download.db-ip.com/free/dbip-city-lite-{YYYY-MM}.mmdb.gz` |
| `GEO_DB_UPDATE_INTERVAL_SECONDS` | `3600` |
| `GEO_DB_PATH` | `data/geo.mmdb` |
| `GEO_DB_READER_PROFILE` | `dbip` (`maxmind` is also supported) |
| `HOST` | `0.0.0.0` |
| `PORT` | `8000` |

`{YYYY-MM}` is replaced with the current UTC month. A URL without the placeholder is used as-is. Copy `.env.example` to `.env` for local runs. After a successful start the service refreshes on the configured interval; a failed refresh is logged and the current reader is kept.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The image is `python:3.14-slim` and runs a single uvicorn process. `HEALTHCHECK` probes `/healthz`. The start download needs outbound HTTPS.

## Tests

```bash
pytest
```

Unit tests mock the MMDB reader and HTTP. They do not download a database or call ip-api.com.

## Manual evaluation scripts

Both scripts are **manual operator tools**. Generated IP lists and compare reports are gitignored and must not be committed. They are not part of a required CI pipeline.

Generate about 1000 random Indian IPs from the local MMDB (per-state quota, best effort). Coverage is printed to stderr:

```bash
python scripts/generate_india_ips.py --db data/geo.mmdb --output ips.txt --count 1000
```

Compare the running service to ip-api.com (English state names, ≤45 ip-api requests/min). The CSV lists **mismatches only**: IP, expected name (ip-api), service DB name, and `note=synonym` when the names are known aliases (e.g. Delhi / NCT of Delhi). Progress for resume is tracked in `report.csv.done`.

```bash
python scripts/compare_ips.py --input ips.txt --output report.csv --base-url http://127.0.0.1:8000
```

Re-running with the same `--output` skips IPs already listed in the `.done` file.
