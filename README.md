# IP to Location Service

Small FastAPI service that maps an IPv4 or IPv6 address to country and region using local [IP2Location](https://www.ip2location.com/) LITE DB3 BIN databases (separate IPv4 and IPv6 files). India (region / state name accuracy) is the evaluation focus.

This site or product includes IP2Location LITE data available from https://lite.ip2location.com.

## Requirements

- Python 3.14
- pip (do not use uv)
- An IP2Location download token (`IP2LOCATION_TOKEN`) from the [file download](https://www.ip2location.com/file-download) portal

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set IP2LOCATION_TOKEN in .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On start the process **must** download and open both LITE DB3 BIN packages (`DB3LITEBIN` and `DB3LITEBINIPV6`). If either download or open fails the process exits, even when older BIN files are already on disk.

```bash
curl 'http://127.0.0.1:8000/v1/location?ip=49.36.1.1'
curl 'http://127.0.0.1:8000/healthz'
```

A successful lookup is a thin JSON document:

```json
{
  "ip": "49.36.1.1",
  "country": "IN",
  "region": "Maharashtra",
  "found": true
}
```

`GET /healthz` returns 200 only when both BIN readers are open.

## Environment

| Variable | Default |
|---|---|
| `IP2LOCATION_TOKEN` | _(required)_ download token |
| `GEO_DB_IPV4_CODE` | `DB3LITEBIN` |
| `GEO_DB_IPV6_CODE` | `DB3LITEBINIPV6` |
| `GEO_DB_IPV4_PATH` | `data/IP2LOCATION-LITE-DB3.BIN` |
| `GEO_DB_IPV6_PATH` | `data/IP2LOCATION-LITE-DB3.IPV6.BIN` |
| `GEO_DB_UPDATE_INTERVAL_SECONDS` | `86400` |
| `GEO_DB_DOWNLOAD_BASE_URL` | `https://www.ip2location.com/download` |
| `HOST` | `0.0.0.0` |
| `PORT` | `8000` |

Copy `.env.example` to `.env` for local runs. After a successful start the service refreshes on the configured interval; a failed refresh is logged and the current reader pair is kept. A successful refresh replaces both files together.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The image is `python:3.14-slim` and runs a single uvicorn process. `HEALTHCHECK` probes `/healthz`. The start download needs outbound HTTPS and a valid token.

## Tests

```bash
pytest
```

Unit tests mock the BIN readers and HTTP. They do not download a database or call ip-api.com.

## Manual evaluation scripts

Both scripts are **manual operator tools**. Generated IP lists and compare reports are gitignored and must not be committed. They are not part of a required CI pipeline.

Generate about 1000 random Indian IPs by sampling public IPv4/IPv6 space against the local BINs (soft per-region quota, best effort). Coverage is printed to stderr:

```bash
python scripts/generate_india_ips.py \
  --ipv4-db data/IP2LOCATION-LITE-DB3.BIN \
  --ipv6-db data/IP2LOCATION-LITE-DB3.IPV6.BIN \
  --output ips.txt --count 1000
```

Compare the running service to ip-api.com (English region names, ≤45 ip-api requests/min). The CSV lists **mismatches only**: IP, expected region (ip-api), service region, and `note=synonym` when the names are known aliases (e.g. Delhi / NCT of Delhi). Progress for resume is tracked in `report.csv.done`.

```bash
python scripts/compare_ips.py --input ips.txt --output report.csv --base-url http://127.0.0.1:8000
```

Re-running with the same `--output` skips IPs already listed in the `.done` file.
