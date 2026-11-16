# ADR-0008: Decision-first Telegram experience and bot identity

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Rule ids affected: R-COMMAND-1, R-PRESENTATION-1, R-ARCHIVE-1

## Context

The first command grid was functional but read like operational debug output. Alerts repeated labels,
used raw ISO dates, duplicated tags, and ended with a text link. Recent archive entries could not be
opened because the SQLite `seen` table did not retain their URLs. The bot also lacked a product mark.

## Decision

Use one restrained radar-operations voice across startup, alerts, commands, empty states, and errors.
Give each emoji one stable meaning. Lead alerts with the opportunity title, format known dates for
humans, keep provider descriptions outside Markdown entities, and attach a one-tap inline URL button.
Personalize the private command desk with `BOT_OWNER_NAME`. Store source URLs in `seen` through an
additive migration so Fresh finds can be opened. Keep the standard slash menu to `/start` and `/grid`.
Version the SVG/JPG avatar and apply it through the official `setMyProfilePhoto` API using the project
bot token. Keep emojis in the navigation grid, not the command bodies; preserve authored line breaks
and enforce compact per-view line budgets.

## Consequences

The owner can judge an opportunity faster and reopen recent captures without searching the chat.
Legacy databases retain all rows, although old rows have no URL until the same listing is captured in
a future database. Telegram owns typography, colors, dark mode, hit targets, and native keyboard
motion; the repository owns information hierarchy, copy, emoji semantics, and the avatar.

## Reversal condition

Move archive browsing to a web app if the owner needs search, saved lists, reminders, or filters that
cannot fit comfortably in Telegram's native message and keyboard model.
