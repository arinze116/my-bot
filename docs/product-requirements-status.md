# Hackathon Radar PRD status

Authoritative product direction: owner PRD dated 2026-11-17. Runtime is Python + SQLite on the existing VPS. Times are UTC internally and WAT in owner-facing provenance.

## Scope status

| Requirement | Status | Evidence |
|---|---|---|
| Single-owner Telegram bot, `/start`, help | Implemented | Owner lock and command tests |
| At least five listing sources plus X | Implemented | Devpost, Devfolio, DoraHacks, ETHGlobal, MLH, Lablab/Starfield, HackerEarth, Gitcoin, optional X |
| Cross-source canonical dedupe | Implemented | Canonical event/store tests |
| New, material change, deadline, ongoing modes | Implemented | Planner, aggregator, event-card, and digest tests |
| Region, stack, mode, minimum-prize filters | Implemented | `/filters` persistence and planner tests |
| Event store and alert history | Implemented | Additive SQLite schema |
| Source health in Telegram | Implemented | `/sources` plus three-failure warning |
| Quiet hours 00:30–06:30 WAT | Implemented | Queue and flush tests |
| Pause, resume, event/domain mute | Implemented | Owner control and callback tests |
| Add, list, and remove bookmarks | Implemented | Persistent store, command, callback, and alert-action tests |
| Daily ongoing digest | Implemented | Once-per-WAT-day digest with 24-hour New/Change suppression |
| Queued-alert control revalidation | Implemented | Due alerts re-check current event/source/domain mutes and filters |
| Silent empty-source detection | Implemented | Explicit empty-result policy plus existing three-failure warning |
| Truthful runtime status | Implemented | Persisted cycle outcome and source-health summary in `/status` |
| SQLite backup and restore | Deployed | Online snapshot, integrity check, guarded restore, active timer, and production drill |
| Off-host backup and recovery drill | Locally verified | Telegram candidate upload, download, SHA-256 check, isolated restore, and stable-message retention tests |
| Crowding heuristic | Pending | No reliable cross-source field verified |
| JSON/CSV export | Pending | v1.1 |
| Codex hand-off action | Pending | v1.1; no outbound action without owner approval |
| Luma connector | Unavailable | Official search requires sign-in; see source research |
| Organiser-account X watch list | Pending | Keyword search remains implemented |

## Acceptance tests

| ID | Status | Evidence |
|---|---|---|
| AT1 owner-only alerts and commands | Passed | Unauthorized-chat and callback tests |
| AT2 two sources, one event and New alert | Passed | `test_cross_source_event_sends_one_new_alert` |
| AT3 deadline change becomes Material change | Passed | Store/planner tests |
| AT4 `/ongoing` excludes ended/upcoming | Passed | Store and command tests |
| AT5 quiet hours queue and flush | Passed | Aggregator/planner tests |
| AT6 broken source warning after streak | Passed | Source-health tests |
| AT7 unresolved URL suppressed | Passed | URL verifier and aggregator tests |
| AT8 recap-only X post rejected | Passed | Twitter filter tests |
| AT9 mute/filter changes cancel queued delivery | Passed | Queued-alert control regression |
| AT10 unexpected zero-result catalog degrades health | Passed | Empty-source policy tests |
| AT11 backup round-trip preserves current and recovery databases | Passed | Backup, restore, CLI, and deployment tests |

## Remaining product limits

Completeness across the public internet is not guaranteed. Scraped provider contracts can drift.
Crowding is unknown where providers expose no applicant/popularity field. Telegram off-host backup
is cloud-stored rather than end-to-end encrypted and retains one latest verified snapshot rather
than multi-version history.
