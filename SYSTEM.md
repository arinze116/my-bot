# SYSTEM.md — Hackathon Radar decisions and numbers

## Purpose and users

- What it does: polls hackathon listings, normalises new entries, archives successful deliveries, and sends Telegram DMs.
- Users: one owner — **1 TARGET**, supplied PRD dated 2026-11-16.
- Main flow: scheduled poll -> parallel source reads -> validation -> deduplication -> immediate per-item Telegram send -> SQLite mark.

## Load and data

| Item | Value | Label | Source |
|---|---:|---|---|
| Poll frequency | 72 cycles/day (1,296,000 / 1,200 seconds) | TARGET | 20-minute PRD interval |
| Outside reads | about 20/cycle, 1,440/day | GUESS | up to 12 listing reads plus 8 X queries |
| Peak source concurrency | 8 calls | TARGET | one worker per enabled source |
| New records | under 100/day | GUESS | no production history yet |
| Storage growth | about 37 MB/year at 1 KB x 100/day | GUESS | upper-bound worksheet |
| Poll completion budget | under 5 minutes | TARGET | leaves 15 minutes before next cycle |
| RPO / RTO | last successful SQLite write / 30 minutes | TARGET | persistent volume plus process restart |

The system has no inbound public endpoint and no request-per-second serving load. Its burst is at most eight outbound reads in flight. Backup RPO after a host-volume failure is **Unknown** until a backup and restore drill exists.

## Consistency

| Data | Class | Why |
|---|---|---|
| `seen` notification records | CONSISTENT | duplicate prevention depends on it |
| source listing content | EVENTUAL | upstream pages can change between polls |
| startup/source status | EVENTUAL | informational only |

## Rules

- **R-TIMEOUT-1:** every outside call has a connect/read/write/pool timeout no greater than 20 seconds.
- **R-SECRET-1:** credentials never enter source control or log messages; Telegram token-bearing URLs are never logged.
- **R-DEDUP-1:** a successful notification is inserted with a unique SHA-1 id; a known id is never sent again.
- **R-DELIVERY-1:** a failed Telegram write is not marked seen and is retried at most three times with the PRD's five-second backoff.
- **R-BOOTSTRAP-1:** the safe default baselines each source on its first successful read; historical notifications require explicit `--notify-existing` intent.
- **R-SCHEDULE-1:** one polling cycle may run at a time; source failures are isolated and do not cancel successful sources.
- **R-RUNTIME-1:** production runs the repository's virtualenv through a version-controlled systemd unit, loads the explicit project environment file without overriding service-provided values, and restarts after failure.
- **R-DISCOVERY-1:** X searches cover the owner's core, call-to-action, ecosystem, regional, niche, and platform terms in no more than eight 512-character queries; specified retrospective, course, bootcamp, and ex-hackathon hiring noise is discarded before delivery.

## Architecture

Python 3.11+ modular monolith running as one systemd-managed background worker. APScheduler triggers the orchestrator. Stateless source modules perform bounded reads in parallel. The orchestrator serialises delivery decisions through SQLite. Telegram and X use their HTTP APIs directly because only one endpoint from each API is needed; this avoids heavyweight wrappers and keeps retry/timeout behaviour explicit. X discovery uses eight bounded query groups and local noise rejection before normalization. See `docs/adr/0001-python-worker-and-direct-http.md`, `docs/adr/0002-vps-systemd-runtime.md`, and `docs/adr/0003-x-discovery-query-groups.md`.

## Known limits

- Telegram has no idempotency key for `sendMessage`. A process crash after Telegram accepts a message but before SQLite commits can cause one duplicate; choosing the opposite order could permanently miss a notification.
- Scraped or undocumented upstream contracts can change without notice. Parser fixtures prove known shapes, not future provider compatibility.
- "Zero missed hackathons" across the public internet cannot be guaranteed. This worker covers enabled sources that remain accessible.
- X recent search is relevance- and recency-limited; exact phrases, language filtering, API access, and a 100-result cap can still omit announcements.
- Free-host availability and persistence depend on the provider plan and volume configuration.
