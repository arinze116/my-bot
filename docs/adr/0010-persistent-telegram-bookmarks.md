# ADR-0010: Persistent Telegram bookmarks

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Rule ids affected: R-COMMAND-1, R-CONTROL-1, R-PRESENTATION-1

## Context

Canonical events already carried an `interested` SQLite flag and alerts exposed an Interested
callback, but the owner could not open a saved-event view or remove an item. Adding a second
bookmark table would duplicate the same one-owner boolean state and strand existing saved records.

## Decision

Treat `events.interested` as the deployed bookmark flag. Rename the alert action to Bookmark while
continuing to accept legacy `interest:` callbacks from messages already in Telegram. Add a
Bookmarks grid view, `/bookmarks`, `/bookmark <event id or URL>`, and
`/unbookmark <event id or URL>`. Accept unique event-id prefixes of at least eight hexadecimal
characters. Show one linked event per line and one inline Remove button per bookmark. After a
Remove callback, persist the change first, acknowledge it, and edit the list message in place.

## Alternatives considered

- **New bookmarks table:** clearer naming, but duplicates a one-bit relation and requires migrating
  existing Interested records.
- **Typed commands only:** simpler transport, but makes routine mobile removal unnecessarily hard.
- **Delete the event row:** violates the audit/archive requirement and would lose sightings and
  alert history.

## Consequences

Existing Interested records appear as bookmarks without schema migration. Bookmark state survives
normal restarts and remains owner-only. Inline callback data stays below Telegram's 64-byte limit:
the longest value is `unbookmark:` plus a 40-character event id. The internal column name remains
`interested` for compatibility even though the product language is Bookmark.

## Reversal condition

Introduce a separate relation if bookmarks gain notes, folders, multiple owners, ordering, or other
metadata that no longer fits one boolean per canonical event.
