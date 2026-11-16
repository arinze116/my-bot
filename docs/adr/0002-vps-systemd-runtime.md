# ADR-0002: VPS systemd runtime uses the project virtualenv

- Date: 2026-11-16 Africa/Lagos
- Status: accepted
- Rule ids affected: R-RUNTIME-1, R-SECRET-1, R-SCHEDULE-1

## Context

The first production smoke command used the VPS system Python and failed before startup because Beautiful Soup existed only in `.venv`. No systemd unit was actually installed. Manual runs also needed a safe way to read the project `.env` without copying credentials into commands or source control.

## Decision

Keep one project virtualenv at `/home/ubuntu/my-bot/.venv`. Pin the complete requested runtime dependency set in `requirements.txt`. Load `/home/ubuntu/my-bot/.env` with `override=False` for manual execution. Install the version-controlled `deploy/hackathon-radar.service`, whose `ExecStart` uses `.venv/bin/python`, whose working directory is the repository, and whose environment file is the same project `.env`.

## Alternatives considered

- **Install packages into system Python:** rejected because it couples the bot to node-wide packages and recreates interpreter drift.
- **Duplicate a second `venv/`:** rejected because `.venv` already exists and passes the deterministic suite.
- **Rely only on shell activation:** rejected because systemd does not activate interactive shell environments.

## Consequences

Shell, smoke-test, and service execution share one interpreter. The unit path is VPS-specific and must change if the repository moves. SDK packages requested by the owner are installed even though the current implementation deliberately uses direct HTTP clients.

## Reversal condition

Revisit if the worker moves into a container, a deployment platform supplies an immutable runtime, or the repository path changes.
