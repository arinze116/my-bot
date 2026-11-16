# ADR-0007: Owner-only Telegram command grid

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Rule ids affected: R-COMMAND-1, R-TIMEOUT-1, R-SECRET-1

## Context

Hackathon Radar was outbound-only. The owner asked for more useful features, bot customization, and
a grid command instead of a long command list. Telegram's standard command menu is always a list,
but a native reply keyboard can present a persistent two-column grid.

## Decision

Run one isolated `getUpdates` thread beside APScheduler. Accept commands only from
`TELEGRAM_CHAT_ID`. Register only `/start` and `/grid` in the standard menu; both open a six-tile
native keyboard for status, latest captures, archive stats, active sources, help, and hide. Set the
bot name and descriptions idempotently through the official Bot API on startup.

## Alternatives considered

- **Telegram command list only:** simpler, but cannot satisfy the requested grid interaction.
- **Inline callback keyboard:** polished, but adds callback acknowledgement/state handling without
  improving this small private dashboard.
- **python-telegram-bot application runtime:** capable, but duplicates lifecycle, retries, and HTTP
  behavior already implemented directly for this single-user worker.

## Consequences

The owner gets a discoverable dashboard and archive visibility without a web app. The bot token can
have only one long-poll consumer; another `getUpdates` process or a webhook will conflict. Command
network failures remain isolated from scheduled discovery.

## Reversal condition

Move to webhooks or the Telegram SDK if the bot becomes multi-user, needs callback-heavy workflows,
or must scale beyond one private chat.
