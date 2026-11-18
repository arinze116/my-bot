# Completion report — operational reliability tranche

Date: 2026-11-18 (Africa/Lagos)
Branch: `feat/hackathon-radar-v1`

## Requested

Proceed with the prioritized Hackathon Radar reliability improvements: current-control delivery,
silent source-drift detection, SQLite backup/restore, truthful status, and accurate shorthand prize
parsing.

## Implemented

- Rechecked event mutes and current filters before direct and queued canonical delivery. Queued
  alerts made ineligible by an owner action are removed without sending.
- Added an explicit source empty-result contract. Catalog sources now enter the existing health
  failure path when they unexpectedly return zero items.
- Added a persisted `runtime_status` record and changed `/status` to report the latest polling
  outcome, source-health summary, delivery failures, and fatal error type.
- Added verified USD shorthand parsing for `K`, `M`, `B`, and their word forms.
- Added online SQLite snapshot creation, integrity verification, collision refusal, atomic
  publication, guarded restore, and automatic pre-restore recovery snapshots.
- Added immutable snapshot verification, temporary-sidecar cleanup, and a second sidecar check that
  stops replacement if a writer appears during the recovery copy.
- Added backup CLI tests and daily systemd backup service/timer templates.
- Updated README, `SYSTEM.md`, `MODULES.md`, product status, ADR-0011, changelog, and RED/GREEN
  evidence.

## Tested

| Command | Status | Current-revision evidence |
|---|---|---|
| queued-alert RED | passed | existing behavior sent a muted queued alert: `assert 1 == 0` |
| empty-source RED | passed | `error_streak` stayed `0`; explicit empty policy was unsupported |
| runtime-status RED | passed | missing `begin_cycle` and `get_runtime_status` contracts |
| status-review RED | passed | delivery failures were not persisted or displayed |
| prize RED | passed | `$50K` parsed as `50`, expected `50000` |
| backup RED | passed | missing module and missing systemd backup unit |
| deployment-sidecar RED | passed | WAL snapshots left `.tmp-shm` and `.tmp-wal` files before cleanup was added |
| focused GREEN | passed | thirteen queue, health, status, prize, source-policy, backup, CLI, and deployment safeguards passed |
| `make smoke-sources` | passed | nine enabled sources passed; expected healthy-empty results were Lablab `0` and Gitcoin `0` |
| systemd unit verification | passed | backup service and timer parsed successfully; warnings concerned unrelated installed units |
| CLI help checks | passed | backup and restore commands exited `0` with documented arguments |
| `git diff --check` | passed | no whitespace errors |
| `make ci` | passed | Ruff passed; pytest `102 passed` |

## Passed

- All requested repository changes and deterministic safeguards.
- Additive SQLite initialization for existing databases.
- PR #1 merged the reliability release as `b7630820fdbc558ecfe6e3209b54d2d7cc176bc3`.
- PR #2 merged the deployment-discovered sidecar fix as
  `070415edc5582f959b39d774605c54ccd2ba43f8`.
- The daily backup timer is installed, enabled, and waiting for its next run.
- A controlled retry restored a byte-identical snapshot and the worker completed a real cycle with
  `fetched=95`, `sent=0`, `source_errors=0`, and zero delivery failures.
- Full lint and regression suite.

## Failed

- The first full gate found two lint issues in the new backup code and CLI test. Both were corrected;
  the repeated full gate passed.
- The first production restore attempt was invalidated when the installed cron watchdog restarted
  the worker during maintenance. The concurrent cycle ended with `no such table: runtime_status`.
  The service was stopped again, the watchdog was paused, and the drill was repeated successfully.
- The successful drill exposed orphan SQLite sidecars for tool-owned temporary snapshots. A failing
  WAL regression test reproduced the defect before the cleanup and mid-restore recheck fix.

## Incomplete

- No retention or off-host copy policy is configured.

## Not verified

- Live Telegram delivery was not run because this revision changes local planning and status copy,
  not the Telegram transport contract.
- Recovery after complete loss of the host volume is not verified because snapshots remain on the
  same host.

## Deployment evidence

- Initial release PR: `https://github.com/arinze116/my-bot/pull/1`.
- Release merge: `b7630820fdbc558ecfe6e3209b54d2d7cc176bc3`.
- Follow-up PR: `https://github.com/arinze116/my-bot/pull/2`.
- Deployed follow-up merge: `070415edc5582f959b39d774605c54ccd2ba43f8`.
- Successful restore source:
  `/home/ubuntu/my-bot/backups/hackathon-radar-20261118T222134.923261Z.sqlite3`.
- Successful pre-restore recovery copy:
  `/home/ubuntu/my-bot/seen_hackathons-pre-restore-20261118T222144.472849Z.sqlite3`.
- Fixed-code unit snapshot:
  `/home/ubuntu/my-bot/backups/hackathon-radar-20261118T223327.698213Z.sqlite3`.
- The fixed-code backup unit added one verified snapshot and added no temporary or snapshot
  sidecars. Its result was `success` with `ExecMainStatus=0`; the snapshot uses mode `600`.
- Twenty orphan sidecars from the original implementation were verified unused and removed. All
  databases, recovery copies, and snapshots remain intact.
- Worker on the deployed follow-up: PID `2601626`, `NRestarts=0`, persisted status `success` with 95
  fetched items and no source or delivery failures.
- The first cycle on `070415e` completed successfully. Its only warning was the expected suppression
  of one unresolved event URL; no error or traceback followed.
- Backup timer: enabled and waiting; next scheduled run was `2026-11-19 00:14:36 WAT`.
- Merged-revision gate: Ruff passed and pytest reported `102 passed` on `070415e`.

## Scorecard evidence

| Criterion | Evidence |
|---|---|
| Engineering | RED/GREEN behavior tests, additive SQLite status record, guarded backup/restore, ADR-0011, and `make ci` with 100 passing tests. |
| Design | `/status` stays within its three-line density budget; no new custom UI was added. |
| Branding | Existing Hackathon Radar command voice and semantic vocabulary remain unchanged. |
| Video | Not applicable: no video artefact was requested. |
| Research | SQLite online backup, integrity, WAL-sidecar, and systemd timer behavior were checked against installed runtime tools and exercised locally; all nine enabled source smoke checks passed. |
| Productivity | One persisted status row and one source policy flag solve the identified gaps without a new service or database. |
| Memory | CORE, relevant Hackathon Radar deployment records, and the deployed canonical baseline were retrieved before implementation. |

## Organisation memory update

Source: this report and `docs/adr/0011-operational-reliability-controls.md`.

Recorded as `fact-20261118-hackathon-radar-operational-reliability-tranche` with subject
`hackathon-radar-reliability`.

```text
instruction: Preserve Hackathon Radar's delivery-time owner-control checks, explicit empty-source contracts, persisted runtime status, and verified SQLite snapshot/restore safeguards.
who: owner and primary engineering agent
why: queued alerts could outlive later mutes, zero-result parser drift appeared healthy, status assumed health, and the archive had no repository-owned recovery path.
where: /home/ubuntu/my-bot aggregator.py, sources.py, event_store.py, commands.py, database_backup.py, and deployment templates
review: when source contracts, queue semantics, persistence, deployment storage, or backup providers change
example: muting an event during quiet hours removes its queued alert; three unexpected empty catalog polls warn once; restore preserves the replaced database first.
```

## Next step

Define retention and copy verified snapshots off host, then run a recovery drill from that off-host
copy.

---

# Completion report — persistent Telegram bookmarks

Date: 2026-11-17 (Africa/Lagos)
Branch: `feat/hackathon-radar-v1`

## Requested

Add owner-only hackathon bookmarks that can be added, listed from a clickable Telegram command,
and removed without deleting the archived event.

## Implemented

- Reused the deployed `events.interested` flag as the bookmark state, preserving existing saved
  events without a destructive migration.
- Added Bookmark actions to canonical alerts and retained legacy `interest:` callback support.
- Added a Bookmarks grid button plus `/bookmarks`, `/bookmark <event id or URL>`, and
  `/unbookmark <event id or URL>`.
- Added inline Remove actions that persist the change and refresh the bookmark list in place.
- Kept all bookmark reads and mutations restricted to the configured owner chat.
- Updated `SYSTEM.md`, `MODULES.md`, ADR-0010, the command UX contract, README, requirements status,
  changelog, and RED/GREEN evidence.

## Tested

| Command | Status | Current-revision evidence |
|---|---|---|
| focused bookmark safeguards | passed | `5 passed` after injected storage/grid/label faults produced `5 failed` |
| owner callback lock | passed | `1 passed` after removing the chat-id guard produced `assert not True` |
| `make ci` | passed | Ruff: `All checks passed!`; pytest: `87 passed` |
| `git diff --check` | passed | no whitespace errors |
| Telegram callback size check | passed | Bookmark payload 49 bytes; Unbookmark payload 51 bytes; official limit 64 bytes |
| Git push | passed | commit `3128ddf` pushed to `origin/feat/hackathon-radar-v1` |
| systemd deployment | passed | PID `2374651`; active/running; `NRestarts=0` after restart |
| first production cycle | passed | `fetched=93`, `sent=0`, `source_errors=0`; job executed successfully |

## Passed

- Persistent add, reload, list, remove, legacy callback compatibility, inline refresh, and owner
  authorization tests.
- Full lint and regression suite.
- Full diff review, including the new ADR.
- Feature commit pushed and the live systemd worker restarted successfully.
- The first scheduled production cycle completed without source errors or duplicate delivery.

## Failed

- No current-revision check failed after restoration.

## Incomplete

- Authenticated Telegram client screenshots were not captured.

## Not verified

- A live Bookmark/Remove tap was not performed; persistence, callback payloads, owner authorization,
  and list refresh behavior are covered by automated tests.

## Scorecard evidence

| Criterion | Evidence |
|---|---|
| Engineering | SQLite persistence tests, owner-lock regression, RED/GREEN evidence, `make ci`, `SYSTEM.md`, `MODULES.md`, ADR-0010. |
| Design | `docs/telegram-command-ui.md` defines the grid, empty state, removal state, density, and Telegram-native interaction; authenticated client screenshots remain unavailable. |
| Branding | Bookmark copy and the 🔖 semantic action follow the existing Hackathon Radar voice and emoji vocabulary. |
| Video | Not applicable: no video artefact was requested. |
| Research | Official Telegram Bot API verified the 1–64 byte callback-data limit; generated payloads are 49/51 bytes. |
| Productivity | The feature reuses the existing one-bit event state and avoids a duplicate table or migration. |
| Memory | Organisation context and the deployed canonical baseline were retrieved before implementation; the local-only bookmark record is superseded after deployment and memory lint reports 0 errors. |

## Next step

Optionally confirm the Bookmarks and Remove buttons visually in the authenticated Telegram client.

---

# Completion report — Hackathon Radar v1

Date: 2026-11-17 (Africa/Lagos)
Branch: `feat/hackathon-radar-v1`

## Requested

Make the supplied single-user Hackathon Radar Telegram bot production-ready on the VPS: use one project virtualenv, verify all source and delivery paths, run it continuously with systemd, harden logs and recovery, and push the verified feature branch without exposing `.env`.

## Implemented

- Modular Python 3.11+ worker with APScheduler and one-cycle-at-a-time execution.
- Parallel, isolated source adapters for Devpost, Devfolio, DoraHacks, MLH, Lablab/Starfield Labs, HackerEarth, Gitcoin, and optional X recent search.
- Corrected 2026 live contracts where the PRD's endpoints had moved or disappeared.
- Standard hackathon schema validation and exact PRD SHA-1 identity formula.
- SQLite `seen` archive plus per-source first-sync state, WAL mode, and busy timeout.
- Safe default baseline that prevents a fresh deployment from flooding Telegram; explicit `--notify-existing` override.
- Telegram Markdown formatting, 4,096-character protection, bounded retries, permanent/retryable error handling, and dependency-log token suppression.
- Source toggles, timing/retry settings, persistent database path, optional X queries, dry-run mode, startup status, and debug source alerts.
- Procfile, environment template, Make commands, README, system/module contracts, research record, ADR, changelog, and restricted license.
- Existing `.venv` completed with the pinned runtime dependencies and used consistently by tests, smoke runs, and systemd.
- Explicit project `.env` loading with process-environment precedence; the real file remains ignored and mode `600`.
- Version-controlled VPS systemd unit with working directory, environment file, virtualenv interpreter, boot enablement, and ten-second restart policy.
- Daily logrotate template, `SystemMaxUse=200M` journald cap, and five-minute watchdog cron.
- Eight bounded X discovery groups covering the owner-supplied event, call-to-action, ecosystem,
  regional, niche, and platform terms, with local filtering for the requested noise patterns.
- Plain escaped description bodies that cannot open an unterminated Telegram Markdown entity.
- Seven high-signal X searches gated by `is_announcement()`, plus concise Telegram alerts that
  omit empty optional fields instead of printing `Not listed`.
- Project `.env` Telegram credentials that cannot be replaced by ambient Codex-agent values.
- Customized bot identity and an owner-only Telegram dashboard with a persistent two-column command
  grid, service/archive/source views, and native empty/error states.
- Premium Telegram experience with decision-first alerts, human-readable dates, one-tap opportunity
  actions, personalized startup/grid copy, a semantic emoji system, clickable Fresh results, and a
  version-controlled radar/code avatar applied through the official profile-photo API.
- Compact command responses that preserve line breaks, remove decorative body emojis, cap Fresh at
  four results and Vault at five source rows, and enforce explicit per-view line budgets.

## Tested

| Command | Status | Current-revision evidence |
|---|---|---|
| `make ci` | passed | Ruff: `All checks passed!`; pytest: `49 passed` |
| `.venv/bin/python main.py --run-once` | passed | exit `0`; fetched 209; zero source errors; all eight source states initialized |
| `.venv/bin/python -m scripts.check_sources` | passed | Devpost 18; Devfolio 20; DoraHacks 13; MLH 24; Lablab 0; HackerEarth 3; Gitcoin 0; X 132; every adapter reported `PASS` |
| Telegram delivery probe through `TelegramClient` | passed | `Telegram delivery confirmed: True`; one explicit deployment smoke message confirmed |
| X recent search | passed | 131 X/Twitter records returned and baselined by the smoke cycle |
| expanded X discovery | passed | all 8 default query groups accepted by X; 625 unique results after noise filtering |
| expanded-query rollout baseline | passed | 625 X results fetched; 590 newly archived without delivery to prevent a historical alert flood |
| Telegram formatter regression | passed | formerly failing escaped-handle/trailing-URL payload returned `True` from the live API |
| high-signal Twitter filter | passed | 11 live announcement-oriented results, down from the original 132; observed first-person recap removed |
| quality-filter smoke run | passed | fetched 89; sent 4; skipped 85; zero source errors |
| concise Telegram formatting | passed | empty/`None`/`Not listed` fields omitted; smoke delivered 4 alerts without formatter failures |
| premium alert rollout | passed | immediate poll delivered one real redesigned alert with inline action; fetched 89, skipped 88, source errors 0 |
| compact command rollout | passed | line breaks preserved; decorative body emojis removed; live three-line grid delivered through the project bot |
| private command grid | passed | personalized `Pulse/Fresh/Vault/Coverage/Guide/Hide` grid delivered through the project bot |
| bot customization | passed | live getters confirmed name, full/short descriptions, minimal `/start` + `/grid` menu, and profile photo |
| archive URL migration | passed | production database migrated additively; newest archive row retains its clickable URL |
| 60-second systemd stability check | passed | active/running; PID `2210943`; `NRestarts=0`; uptime `1min 2s` |
| first scheduled systemd poll | passed | fetched 209; skipped 209; source errors 0; APScheduler logged `executed successfully` |
| two-minute journal follow | passed | no warning, error, crash, or restart appeared |
| host hardening verification | passed | logrotate parsed one rule; journald contains `SystemMaxUse=200M`; watchdog visible in `crontab -l` |
| `.venv/bin/python -m compileall -q -x '/\.venv/' .` | passed | `compileall: PASS` |
| `.venv/bin/python main.py --help` | passed | documented all four runtime flags |
| `git diff --check` | passed | no whitespace errors |
| repository credential-pattern scan | passed | no Telegram, GitHub, Xox, bearer-token, or private-key signature found |

## RED then GREEN evidence

`docs/evidence/RED_GREEN.md` records the injected fault, failing assertion, restoration, and passing evidence for:

- R-TIMEOUT-1 bounded outside-call timeout.
- R-DELIVERY-1 three-attempt retry bound and failed-send persistence.
- R-SECRET-1 application and dependency log redaction.
- R-BOOTSTRAP-1 first-sync flood prevention.
- R-DEDUP-1 duplicate suppression.
- R-SCHEDULE-1 one polling cycle at a time.
- R-RUNTIME-1 dotenv loading and virtualenv-backed systemd execution.
- R-DISCOVERY-1 requested X keyword coverage, bounded query groups, and noise rejection.

## Passed

- Deterministic unit/contract suite.
- Lint and import/style checks.
- Live read-only validation for all credential-free source adapters.
- End-to-end live fetch, SQLite baseline, X recent search, and Telegram delivery.
- Enabled systemd service stability and immediate APScheduler execution.
- Installed and verified journald, logrotate, and watchdog safeguards.
- Feature-branch, whitespace, unfinished-marker, and secret-pattern checks.

## Failed

- No current-revision check failed.

## Incomplete

- No host-level SQLite backup/restore workflow exists.

## Not verified

- Railway cost and always-on behaviour: official plan details were researched, but actual resource usage requires a deployment.
- Recovery after host-volume loss: no backup restore drill has run.

## Scorecard evidence

| Criterion | Evidence |
|---|---|
| Engineering | `make ci`; 49 tests; RED/GREEN evidence; additive database migration; `SYSTEM.md`; `MODULES.md`; ADRs; live delivery; active systemd service. |
| Design | `docs/telegram-command-ui.md`; native two-column desk; semantic emoji vocabulary; empty/error/recovery states; visual avatar inspection. Telegram-client screenshots remain unavailable. |
| Branding | `brand/hackathon-radar-avatar.svg` and JPG production asset; named palette; consistent Radar voice across alerts, startup, commands, and errors; live Bot API identity verification. |
| Video | Not applicable: no video artefact was requested. |
| Research | `docs/research-2026-11-16.md`; official Telegram/X/Railway references; live endpoint and robots checks; corrected source contracts. |
| Productivity | The fetch-to-alert path, runtime interpreter, service restart policy, scheduler, and host hardening are verified with reproducible commands and live evidence. |
| Memory | Organisation CORE/context were retrieved before work; the prior live command-grid deployment was recorded and linted. The premium-experience deployment is proposed below for the next durable fact. |

## Proposed organisation memory update

Source: this report, ADR-0008, and the live 2026-11-17 rollout.

```text
instruction: Preserve Hackathon Radar's decision-first Telegram voice, semantic emoji mapping, project-token bot identity, clickable Fresh archive, and owner-only native command desk.
who: owner and primary engineering agent
why: the first functional command grid and alerts were technically correct but not product-quality or fully customized.
where: /home/ubuntu/my-bot Telegram formatter, command center, brand assets, and SQLite archive views
review: when adding a command, changing the alert hierarchy, replacing the avatar, becoming multi-user, or changing Telegram API delivery
example: a new alert leads with Radar hit and the title, omits missing fields, formats dates for humans, and provides one View opportunity button.
```

## Next step

Monitor the live worker with `sudo journalctl -u hackathon-radar -f`. Keep the default baseline unless historical alerts are deliberately wanted, and add a tested SQLite backup/restore procedure before relying on the archive as the only copy.
