# SYSTEM.md — Hackathon Radar decisions and numbers

## Purpose and users

- What it does: polls hackathon listings, normalises new entries, archives successful deliveries, and sends Telegram DMs.
- Users: one owner — **1 TARGET**, supplied PRD dated 2026-11-16.
- Main flow: scheduled poll -> parallel source reads -> validation -> deduplication -> immediate per-item Telegram send -> SQLite mark.

## Load and data

| Item | Value | Label | Source |
|---|---:|---|---|
| Poll frequency | 72 cycles/day (1,296,000 / 1,200 seconds) | TARGET | 20-minute PRD interval |
| Outside reads | about 7,128/day | GUESS | 1,368 discovery reads plus up to 5,760 Telegram long polls |
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
- **R-DELIVERY-1:** a failed Telegram write is not marked seen and is retried at most three times with the PRD's five-second backoff; untrusted descriptions are escaped but never wrapped as a Markdown entity; empty optional fields are omitted from alerts.
- **R-BOOTSTRAP-1:** the safe default baselines each source on its first successful read; historical notifications require explicit `--notify-existing` intent.
- **R-SCHEDULE-1:** one polling cycle may run at a time; source failures are isolated and do not cancel successful sources.
- **R-RUNTIME-1:** production runs the repository's virtualenv through a version-controlled systemd unit, uses Telegram credentials from the explicit project `.env` instead of ambient agent credentials, and restarts after failure.
- **R-DISCOVERY-1:** X uses seven high-signal registration/deadline/prize queries and only passes tweets containing an announcement signal; retweets, first-person recaps, courses, bootcamps, ex-hackathon hiring, and participant diaries are discarded before delivery.
- **R-COMMAND-1:** Telegram commands are accepted only from the configured owner chat; command/API failures never stop scheduled polling; `/start` and `/grid` expose a native two-column command keyboard.
- **R-PRESENTATION-1:** Telegram alerts lead with the opportunity, use human-readable dates and one semantic emoji per data type, omit empty fields, escape provider content, and include a direct one-tap action; command responses preserve intentional line breaks and stay within compact per-view density budgets.
- **R-ARCHIVE-1:** successful deliveries retain their source URL for clickable recent views; existing SQLite databases migrate additively without losing legacy rows.

## Architecture

Python 3.11+ modular monolith running as one systemd-managed background worker. APScheduler triggers the orchestrator. Stateless source modules perform bounded reads in parallel. The orchestrator serialises delivery decisions through SQLite. A separate isolated thread long-polls the same project Telegram bot for owner-only commands. Telegram and X use their HTTP APIs directly to keep retry, timeout, and access behavior visible. X discovery uses seven high-signal queries plus `is_announcement()` before normalization. The command surface uses native HTML formatting and the archive retains URLs for clickable recent results. See ADR-0001, ADR-0002, ADR-0005, ADR-0006, ADR-0007, and ADR-0008.

## Known limits

- Telegram has no idempotency key for `sendMessage`. A process crash after Telegram accepts a message but before SQLite commits can cause one duplicate; choosing the opposite order could permanently miss a notification.
- Scraped or undocumented upstream contracts can change without notice. Parser fixtures prove known shapes, not future provider compatibility.
- "Zero missed hackathons" across the public internet cannot be guaranteed. This worker covers enabled sources that remain accessible.
- X recent search is relevance- and recency-limited; exact phrases, language filtering, API access, and a 100-result cap can still omit announcements.
- Free-host availability and persistence depend on the provider plan and volume configuration.
- Telegram permits only one active `getUpdates` consumer for a bot token; another poller or a webhook would conflict with the command thread.
