# ADR-0009: Canonical events and owner-controlled alert planning

- Status: Accepted
- Date: 2026-11-17

## Context

The legacy worker deduplicated only `title + URL`. It could not merge the same event across a listing platform and X, track material deadline changes, answer `/ongoing`, enforce quiet hours, or explain source health. Replacing the legacy table in place would risk losing the live archive.

## Decision

Keep Python and one SQLite database. Add canonical `events`, `sightings`, `alerts_sent`, `source_health`, `user_prefs`, and `queued_alerts` tables beside the legacy `seen` and `source_state` tables.

Canonical identity uses normalized title, canonical URL host, and start date. Exact canonical URLs merge immediately. Different URLs merge only when titles are strongly similar, date ranges overlap, and the sightings share a host. The alert planner produces stable New, Material change, 72-hour, 24-hour, and daily Ongoing digest keys. The runtime reloads owner preferences before each cycle.

Canonical push alerts use HTML, WAT provenance, and native Open/Mute/Interested actions. A bounded HEAD request with GET fallback suppresses dead URLs. The legacy path remains active for dry runs and archive compatibility.

## Consequences

- Cross-source sightings produce one New alert while retaining provenance.
- Existing deployments migrate additively without wiping SQLite.
- Preferences, mutes, interested flags, source health, and quiet-hour queues survive restarts.
- A daily ongoing digest can be idempotent without batching New alerts.
- Similarity matching remains conservative; events with unrelated hosts may stay separate.
- Telegram still has a narrow send-before-commit duplicate window because it offers no idempotency key.

## Reversal trigger

Reconsider SQLite and the in-process planner when the product becomes multi-user, requires independent worker scaling, or exceeds one host's reliable write/concurrency envelope.
