# ADR-0006: Project Telegram credentials override ambient agent values

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Rule ids affected: R-RUNTIME-1, R-SECRET-1

## Context

The VPS interactive environment can expose a Telegram token used by the Codex agent. Standard
`python-dotenv` loading with `override=False` lets that ambient token replace Hackathon Radar's
project token during manual runs, potentially directing messages through the wrong bot.

## Decision

When `/home/ubuntu/my-bot/.env` exists, read `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` directly
from that file. Do not print, log, copy, or commit either value. If the project file does not exist,
retain process-environment fallback for container and managed-host deployments. Other runtime
settings keep normal environment precedence.

## Consequences

Manual smoke tests and the systemd service use the same project bot even when an interactive shell
contains agent credentials. A present project `.env` with missing Telegram keys now fails validation
instead of silently falling back to an unrelated ambient bot.

## Reversal condition

Revisit if credentials move to a dedicated secret manager or the worker is containerized without a
project `.env`.
