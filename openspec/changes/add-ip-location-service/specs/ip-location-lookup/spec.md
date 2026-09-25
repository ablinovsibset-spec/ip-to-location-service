## Purpose

Expose a thin English REST API that maps an IPv4 or IPv6 address to country and administrative state, and a liveness endpoint that confirms the database is open.

## ADDED Requirements

### Requirement: Lookup endpoint accepts IP as query parameter

The service MUST provide `GET /v1/location` and MUST read the address from the `ip` query parameter. The endpoint MUST accept both IPv4 and IPv6 textual forms.

#### Scenario: IPv4 lookup
- **WHEN** a client calls `GET /v1/location?ip=49.36.1.1` and the database contains that address
- **THEN** the service responds `200` with a JSON body describing that address

#### Scenario: IPv6 lookup
- **WHEN** a client calls `GET /v1/location?ip=2405:201:1::1` and the database contains that address
- **THEN** the service responds `200` with a JSON body describing that address

### Requirement: Successful lookup body

A `200` response MUST be a JSON object with English keys `ip`, `country`, `state_iso`, `state_name`, and `found`. `ip` MUST echo the requested address. `country` MUST be the ISO 3166-1 alpha-2 code. `state_iso` MUST be the full ISO 3166-2 code (country, hyphen, subdivision) when a subdivision is present. `state_name` MUST be the English subdivision name when present. `found` MUST be `true`. The body MUST NOT include city or coordinates.

#### Scenario: Indian address with state
- **WHEN** the database maps the IP to country `IN` and subdivision `MH` named `Maharashtra`
- **THEN** the body contains `country`=`IN`, `state_iso`=`IN-MH`, `state_name`=`Maharashtra`, `found`=`true`

#### Scenario: Non-Indian address may omit state
- **WHEN** the database maps the IP to a non-`IN` country and has no subdivision
- **THEN** the service still responds `200` with that `country` and empty `state_iso` and `state_name`

### Requirement: Missing subdivision is still a hit

When the database has a record for the address but no subdivision, the service MUST respond `200` with the country filled and `state_iso` and `state_name` empty (JSON `null`). This MUST apply to Indian and non-Indian addresses. `404` MUST be used only when the database has no record for the address.

#### Scenario: India without state
- **WHEN** the database maps the IP to country `IN` and has no subdivision
- **THEN** the service responds `200` with `country`=`IN` and `state_iso` / `state_name` set to `null`

### Requirement: Invalid address is 400

When the `ip` parameter is missing or is not a valid IPv4 or IPv6 address, the service MUST respond `400` with FastAPI-style `{"detail": "<message>"}`.

#### Scenario: Malformed IP
- **WHEN** a client calls `GET /v1/location?ip=not-an-ip`
- **THEN** the service responds `400` with a JSON object that has a `detail` string

#### Scenario: Missing IP
- **WHEN** a client calls `GET /v1/location` without `ip`
- **THEN** the service responds `400` with a JSON object that has a `detail` string

### Requirement: Unknown or private address is 404

When the address is syntactically valid but has no database record, including private and reserved addresses, the service MUST respond `404` with `{"detail": "<message>"}`.

#### Scenario: Private IPv4
- **WHEN** a client calls `GET /v1/location?ip=10.0.0.1`
- **THEN** the service responds `404` with a JSON object that has a `detail` string

#### Scenario: Public IP absent from database
- **WHEN** a client calls `GET /v1/location?ip=<public address>` and the database has no record
- **THEN** the service responds `404` with a JSON object that has a `detail` string

### Requirement: Health endpoint

The service MUST provide `GET /healthz`. It MUST respond `200` when the process is accepting requests and the MMDB is open. It MUST NOT require an IP parameter.

#### Scenario: Healthy process
- **WHEN** the service has an open database and a client calls `GET /healthz`
- **THEN** the service responds `200`
