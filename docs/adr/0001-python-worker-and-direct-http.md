# ADR-0001: Python worker with direct HTTP API clients

- Date: 2026-11-16 Africa/Lagos
- Status: accepted
- Rule ids affected: R-TIMEOUT-1, R-SECRET-1, R-DELIVERY-1, R-SCHEDULE-1

## Context

The supplied PRD requires a single-user worker, eight source adapters, a 20-minute polling interval, SQLite deduplication, and Telegram delivery. The target is one process with roughly 864 outside reads/day (**GUESS**) and fewer than 100 database writes/day (**GUESS**). Live checks on 2026-11-16 found that several named endpoints had moved or disappeared.

## Decision

Use Python 3.11+, APScheduler 3.x, `httpx`, Beautiful Soup/lxml, and the standard SQLite library. Use the Telegram and X HTTP APIs directly instead of `python-telegram-bot` and Tweepy. Their wrappers add lifecycle and async surface area while this worker needs only `sendMessage` and recent search. Keep each provider behind a stateless `fetch()` adapter and make provider URLs configurable.

Use a safe per-source baseline on first successful fetch. The owner can explicitly choose historical delivery with `--notify-existing`.

## Alternatives considered

- **Full async application with SDK clients:** workable, but adds event-loop and SDK lifecycle complexity to an otherwise synchronous scheduled worker.
- **Provider SDKs plus thread scheduler:** Telegram's current Python SDK is async-first, requiring a sync/async bridge for every send.
- **Notify every current listing on first boot:** matches the literal empty-database flow but can produce dozens of unwanted DMs and rate-limit the bot.

## Consequences

HTTP status, timeout, retry, and redaction behaviour remain visible and testable. We give up SDK convenience and must track API schema changes ourselves. `source_state` is a second SQLite table added solely to make first-sync safety correct for sources that recover after an earlier failure.

## Reversal condition

Adopt an SDK if the bot needs inbound updates, webhooks, rich Telegram workflows, X pagination/state helpers, or if direct API contract maintenance becomes more expensive than the SDK lifecycle.
