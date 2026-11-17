# SYSTEM.md — Hackathon Radar decisions and numbers

## Purpose and users

- What it does: polls hackathon listings, merges source sightings into canonical events, applies owner preferences, and sends idempotent Telegram alerts and digests.
- Users: one owner — **1 TARGET**, supplied PRD updated 2026-11-17.
- Main flow: scheduled poll -> parallel source reads -> validation -> canonical merge -> filter and alert plan -> URL check -> Telegram delivery -> SQLite alert record.

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
| canonical events, sightings, and alerts | CONSISTENT | cross-source dedupe and material-change alerts depend on them |
| owner preferences, mutes, and bookmarks | CONSISTENT | private owner state must survive restarts |
| source listing content | EVENTUAL | upstream pages can change between polls |
| source health and startup status | EVENTUAL | informational and operational, not transactional |

## Rules

- **R-TIMEOUT-1:** every outside call has a connect/read/write/pool timeout no greater than 20 seconds.
- **R-SECRET-1:** credentials never enter source control or log messages; Telegram token-bearing URLs are never logged.
- **R-DEDUP-1:** a successful notification is inserted with a unique SHA-1 id; a known id is never sent again.
- **R-DELIVERY-1:** a failed Telegram write is not marked seen and is retried at most three times with the PRD's five-second backoff; untrusted descriptions are escaped but never wrapped as a Markdown entity; empty optional fields are omitted from alerts.
- **R-BOOTSTRAP-1:** the safe default baselines each source on its first successful read; historical notifications require explicit `--notify-existing` intent.
- **R-SCHEDULE-1:** one polling cycle may run at a time; source failures are isolated and do not cancel successful sources.
- **R-RUNTIME-1:** production runs the repository's virtualenv through a version-controlled systemd unit, uses Telegram credentials from the explicit project `.env` instead of ambient agent credentials, and restarts after failure.
- **R-DISCOVERY-1:** X uses seven high-signal registration/deadline/prize queries and only passes tweets containing an announcement signal; retweets, first-person recaps, courses, bootcamps, ex-hackathon hiring, and participant diaries are discarded before delivery.
- **R-COMMAND-1:** Telegram commands are accepted only from the configured owner chat; command/API failures never stop scheduled polling; `/start` and `/grid` expose a native two-column command keyboard with bookmark access.
- **R-PRESENTATION-1:** Telegram alerts lead with the opportunity, use human-readable dates and one semantic emoji per data type, omit empty fields, escape provider content, and include a direct one-tap action; command responses preserve intentional line breaks and stay within compact per-view density budgets.
- **R-ARCHIVE-1:** successful deliveries retain their source URL for clickable recent views; existing SQLite databases migrate additively without losing legacy rows.
- **R-CANONICAL-1:** matching URLs, or strongly similar titles with overlapping dates and a shared host, merge into one canonical event while retaining every sighting.
- **R-URL-1:** canonical push alerts are suppressed when their registration/event URL does not resolve after HEAD with GET fallback.
- **R-CONTROL-1:** only the owner chat can read or mutate filters, pause state, digest state, mutes, and bookmarks; bookmark add/list/remove state persists in SQLite; preferences reload before each poll cycle.
- **R-HEALTH-1:** source success and failure streaks persist; three consecutive failures produce one owner warning, repeated at most daily until recovery.
- **R-DIGEST-1:** ongoing events are grouped once per WAT day outside quiet hours; events alerted as New or Changed in the previous 24 hours are omitted.

## Architecture

Python 3.11+ modular monolith running as one systemd-managed background worker. APScheduler triggers the orchestrator. Stateless source modules perform bounded reads in parallel. The additive SQLite event store owns canonical events, sightings, alert keys, source health, preferences, bookmarks, and quiet-hour queues while the legacy `seen` table remains for archive compatibility. The alert planner decides New, Material change, Deadline soon, and daily Ongoing digest delivery. A separate isolated thread long-polls the same project Telegram bot for owner-only commands and callbacks. Telegram and X use their HTTP APIs directly so retry, timeout, and access behavior remain visible. See ADR-0009 and ADR-0010.

## Known limits

- Telegram has no idempotency key for `sendMessage`. A process crash after Telegram accepts a message but before SQLite commits can cause one duplicate; choosing the opposite order could permanently miss a notification.
- Scraped or undocumented upstream contracts can change without notice. Parser fixtures prove known shapes, not future provider compatibility.
- "Zero missed hackathons" across the public internet cannot be guaranteed. This worker covers enabled sources that remain accessible.
- X recent search is relevance- and recency-limited; exact phrases, language filtering, API access, and a 100-result cap can still omit announcements.
- Luma discovery is **UNAVAILABLE**: its official discover page does not expose query results server-side and its official client search endpoint requires a signed-in user. The bot does not bypass that control.
- ETHGlobal uses its public official events HTML because the guessed `/api/events` route is 404; card markup can change.
- Crowding scores, CSV/JSON export, organiser-account X watches, and Codex hand-off buttons remain planned rather than implemented.
- Free-host availability and persistence depend on the provider plan and volume configuration.
- Telegram permits only one active `getUpdates` consumer for a bot token; another poller or a webhook would conflict with the command thread.
