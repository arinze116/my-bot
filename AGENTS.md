This codebase is yours to maintain: what it is for and how it is built are your call, and you will keep building on it.

## Outcome

Maintain a small, dependable personal Telegram worker that discovers newly listed hackathons, sends each successful notification once under normal operation, and keeps an auditable SQLite archive.

## Constraints

- Never commit or log Telegram or X credentials.
- Keep source adapters isolated: one source failure must not stop the polling cycle.
- Treat remote HTML and JSON as untrusted input and validate required fields before delivery.
- Update `SYSTEM.md`, `MODULES.md`, and an ADR when a source contract or delivery invariant changes.
- Publishing, pushing, deploying, or changing live services requires the owner's explicit approval.

## Completion

Run `make ci` and review the full diff before calling a revision complete. Risky rule changes also require recorded RED then GREEN evidence.
