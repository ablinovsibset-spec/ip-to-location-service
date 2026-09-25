## Purpose

Keep a local MMDB file available for lookups by downloading it on start, refreshing it on a schedule, and letting operators replace the provider through environment configuration.

## ADDED Requirements

### Requirement: Configuration through environment

The service MUST read database settings only from the environment. A local `.env` file is accepted as a way to populate that environment in development. The environment MUST configure at least: download URL or URL template, refresh interval, local MMDB path, and reader profile (`dbip` or `maxmind`). The default refresh interval MUST be one hour. The default URL template MUST target DB-IP City Lite using a `{YYYY-MM}` month placeholder.

#### Scenario: Default provider
- **WHEN** the operator starts the service with no database URL override
- **THEN** the service downloads DB-IP City Lite for the current UTC month using the documented URL template

#### Scenario: Replace provider
- **WHEN** the operator sets a different URL (or template), interval, path, and profile
- **THEN** the service downloads that file, stores it at the configured path, and interprets records with the configured profile

### Requirement: Successful download required at start

The process MUST download and open an MMDB before it accepts lookup traffic. If that download and open do not succeed, the process MUST exit even if an older file already exists on disk. A download of the previous UTC month MUST count as success when the current month file is unavailable.

#### Scenario: Fresh start
- **WHEN** the current-month file downloads and opens
- **THEN** the process stays up and serves lookups from that file

#### Scenario: Current month missing
- **WHEN** the current-month URL returns not found and the previous-month file downloads and opens
- **THEN** the process stays up and treats the start as successful

#### Scenario: No usable download
- **WHEN** both current and previous month downloads fail (or the configured literal URL fails) 
- **THEN** the process exits and does not serve lookups, even if a local MMDB file is already present

### Requirement: Scheduled refresh keeps serving on failure

After a successful start, the service MUST attempt to download a replacement MMDB on the configured interval. If a refresh fails, the service MUST keep serving lookups from the already open database and MUST record the failure in the log. A successful refresh MUST replace the open database without dropping in-flight lookups.

#### Scenario: Refresh fails
- **WHEN** an hourly download fails after the process is already serving traffic
- **THEN** lookups continue to use the previously opened database and the failure is logged

#### Scenario: Refresh succeeds
- **WHEN** a newer file downloads and opens
- **THEN** subsequent lookups use the new database and in-flight lookups complete against a consistent open reader

### Requirement: Reader profiles

The service MUST map MMDB records through a named profile. Built-in profiles MUST include `dbip` and `maxmind` for city-schema files that expose country ISO code and a subdivisions list. The default profile MUST be `dbip`.

#### Scenario: Default profile
- **WHEN** no profile is set
- **THEN** the service interprets records as DB-IP city-lite fields

#### Scenario: MaxMind profile
- **WHEN** the operator sets the profile to `maxmind`
- **THEN** the service interprets country and subdivision fields using the MaxMind city schema mapping
