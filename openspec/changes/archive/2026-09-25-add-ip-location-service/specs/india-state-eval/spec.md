## Purpose

Provide manual scripts that build a random India-focused IP list and compare the running service to ip-api.com at state-name accuracy, without committing IP fixtures to the repository.

## ADDED Requirements

### Requirement: Random India list with per-state quota

The repository MUST include a generator script that writes a text file with one IP address per line. The generator MUST sample random IPv4 and IPv6 addresses from Indian ranges in the local MMDB (whatever mix those ranges yield). It MUST aim for an equal per-state quota totaling about 1000 addresses, using the local MMDB English subdivision name as the quota label (falling back to subdivision ISO, then `UNKNOWN`, when the name is missing). When a state cannot fill its quota, the generator MUST keep the addresses it found and MUST report coverage per state. It MUST NOT fail solely because some states are thin.

#### Scenario: Target size
- **WHEN** an operator runs the generator against an open India-capable MMDB
- **THEN** the output file contains up to about 1000 unique IPs, one per line, and a coverage summary of how many addresses landed in each state

#### Scenario: Thin state
- **WHEN** a state or union territory has fewer MMDB ranges than the quota
- **THEN** the generator writes however many it could sample for that state and continues with the rest

### Requirement: Compare script uses ip-api and the running service

The repository MUST include a compare script that takes the IP text file as input. For each address it MUST query the running service and ip-api.com. It MUST treat ip-api.com as the public reference. It MUST write a CSV report that contains **mismatch rows only**, with at least: IP, expected state name (ip-api), and service state name (service DB). Matching addresses MUST NOT appear in the report.

#### Scenario: Input file
- **WHEN** an operator runs the compare script with a one-column IP file and a reachable service
- **THEN** the script produces a CSV containing one row per mismatched IP with expected and service state names

### Requirement: Verdict is English state name

The verdict MUST compare English subdivision names only. The script MUST compare the service `state_name` to ip-api `regionName` after normalizing whitespace and case. ISO codes MAY appear in the report and MUST NOT affect the verdict. When the service returns `200` and ip-api reports `fail` or an empty region name, the verdict MUST be mismatch. Transport errors and HTTP 429 from ip-api MUST be retried and MUST NOT be recorded as mismatch until retries are exhausted.

#### Scenario: Matching names
- **WHEN** the service returns `state_name`=`Maharashtra` and ip-api returns `regionName`=`Maharashtra`
- **THEN** the verdict is match

#### Scenario: Case or whitespace difference
- **WHEN** both sides name the same state with different letter case or extra spaces
- **THEN** the verdict is match

#### Scenario: Reference gap
- **WHEN** the service returns `200` and ip-api returns `status=fail` or an empty `regionName` after successful HTTP
- **THEN** the verdict is mismatch

### Requirement: Resumable compare run

The compare script MUST write mismatch rows incrementally and MUST track every processed address (match or mismatch) in a sidecar progress file next to the output CSV so resume works even when matches are omitted from the report.

#### Scenario: Resume after interrupt
- **WHEN** the script has processed 400 addresses and is started again with the same input file and output CSV
- **THEN** it does not re-query those 400 addresses and continues with the remainder

### Requirement: Scripts are manual and fixture-free

Unit tests MUST mock the MMDB reader and external HTTP; they MUST NOT require a live 1000-IP run. The repository MUST NOT commit generated IP lists or compare reports as fixtures. The 1000-IP compare run is a manual operator action and MUST NOT be part of a required CI pipeline.

#### Scenario: Everyday tests
- **WHEN** a developer runs the unit test suite
- **THEN** the suite completes without calling ip-api.com and without a 1000-row IP file
