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

## Remaining product limits

Completeness across the public internet is not guaranteed. Scraped provider contracts can drift. Crowding is unknown where providers expose no applicant/popularity field. Host backup and restore remain unverified.
