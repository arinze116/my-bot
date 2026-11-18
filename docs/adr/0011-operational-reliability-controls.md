# ADR-0011: operational reliability controls

Date: 2026-11-18
Status: accepted; host deployment verified

## Context

Quiet-hour alerts persisted their original plan but did not recheck later owner controls. A source
that returned zero items reset its failure streak even when its catalog contract normally contains
listings. `/status` described the process configuration rather than the last polling outcome. The
SQLite archive also had no repository-owned backup and restore path. Shorthand prizes such as
`$50K` were parsed as `50`, which made minimum-prize filtering inaccurate.

The first production restore attempt exposed two host-specific hazards. The installed cron
watchdog restarted the worker during maintenance, and SQLite left WAL/SHM files for temporary
snapshot names. The concurrent cycle failed after the database path was replaced. The retry paused
the watchdog and completed without a writer.

## Decision

- Recheck event mute state and current filters before every direct or queued canonical delivery.
  Remove queued alerts made ineligible by current owner controls.
- Add `SourceSpec.empty_result_is_valid`. Treat zero items as a source failure unless the source
  explicitly allows an empty filtered result.
- Persist one `runtime_status` record with the latest cycle start, completion, outcome, fetched
  count, sent count, source-error count, delivery-failure count, and fatal error type. Use it for
  `/status`.
- Parse verified USD values with `K`, `M`, `B`, `thousand`, `million`, and `billion` multipliers.
- Create SQLite snapshots through the online backup API. Verify integrity before atomic publication.
  Require explicit replacement for restore, preserve the current database as a recovery snapshot,
  and refuse restore while WAL/SHM sidecars exist. Verify closed snapshots through immutable reads,
  remove sidecars for tool-owned temporary files, and recheck the destination after the recovery
  snapshot so a writer that appears mid-restore aborts before replacement.
- Pause any external restart watchdog during a restore window. Restore it only after the worker
  completes a real polling cycle on the recovered database.
- Ship a daily systemd timer template but do not install or enable it without owner approval.

## Alternatives considered

Deriving status from `source_health` alone avoided a table but could not distinguish a running,
completed, or failed cycle. Treating every zero result as healthy preserved current behavior but hid
parser drift. Treating every zero result as failed created false warnings for filtered sources such
as Lablab, Gitcoin, HackerEarth, and X. Copying the SQLite file directly was rejected because WAL
state could produce an inconsistent snapshot.

## Consequences

- Owner controls apply at delivery time, including alerts queued before a preference change.
- Catalog adapters must choose their empty-result contract when registered.
- `/status` remains truthful across command-thread and process restarts because the latest state is
  stored in SQLite.
- Backup works while the worker is running. Restore remains an explicit maintenance action with a
  stopped worker and paused watchdog.
- The daily timer and host-local restore path are verified. Full host-volume-loss recovery remains
  unverified until snapshots are copied off host with a tested retention policy.

## Reversal trigger

Replace the single-row status record with run history when operational analytics require more than
the latest outcome. Replace filesystem snapshots when the deployment gains managed database backup
or off-host object storage with tested restoration.
