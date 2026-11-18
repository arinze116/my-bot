# MODULES.md — module contracts

## source adapters

- **Owns:** no persistent state; one provider contract per `scrapers/<source>.py`.
- **Promises:** `fetch() -> list[dict]`; required `title`, `url`, and `platform` values are non-empty; outside calls obey R-TIMEOUT-1; remote fields are treated as untrusted; X results pass `is_announcement()` and obey R-DISCOVERY-1; each `SourceSpec` declares whether an empty filtered result is valid.
- **Depends on:** public provider pages/APIs, whose availability and schemas have no common SLA.
- **Fails how:** raises a source-scoped exception; the orchestrator logs it and continues other sources.
- **Hard part:** detecting provider contract drift without creating false alerts.
- **Red tests:** `test_http_client_uses_bounded_timeouts` -> R-TIMEOUT-1; `test_is_announcement_rejects_recap`, `test_is_announcement_accepts_listing`, and `test_twitter_fetch_filters_requested_noise` -> R-DISCOVERY-1; parser fixture tests -> source contracts.

## aggregator

- **Owns:** source execution order, within-cycle deduplication, first-sync policy, and delivery-to-database sequencing.
- **Promises:** source isolation (R-SCHEDULE-1); known ids do not send (R-DEDUP-1); safe first sync does not flood Telegram (R-BOOTSTRAP-1); canonical plans reload preferences every cycle; current owner controls are rechecked before direct or queued delivery; unexpected empty catalogs enter source health as failures; cycle status persists; delivery exceptions stay isolated; daily digests obey R-DIGEST-1.
- **Depends on:** adapters, legacy `Database`, `EventStore`, `AlertPlanner`, `URLVerifier`, and `TelegramClient`.
- **Fails how:** a source error is recorded and skipped; a delivery failure remains unseen for a later cycle.
- **Hard part:** the unavoidable ambiguity between a remote Telegram write and the local SQLite commit.
- **Red tests:** `test_failed_delivery_is_not_marked_seen` -> R-DELIVERY-1; `test_baseline_marks_without_sending` -> R-BOOTSTRAP-1; `test_duplicate_is_sent_once` -> R-DEDUP-1; `test_due_queue_is_discarded_after_event_is_muted` -> R-CONTROL-1; empty-source and cycle-status tests -> R-HEALTH-1/R-STATUS-1.

## canonical event model and store

- **Owns:** stable event identity, URL/title normalization, status derivation, inferred region/stack tags, canonical event rows, sightings, alert keys, source health, preferences, mutes, bookmarks, quiet-hour queues, and the latest runtime status.
- **Promises:** cross-source merges follow R-CANONICAL-1; legacy rows remain intact; material prize/deadline/status changes are explicit; bookmark state uses the existing `interested` column and survives restarts; all writes are additive SQLite transactions.
- **Depends on:** the same SQLite file as the legacy archive and UTC timestamps.
- **Fails how:** malformed optional fields become unknown/empty; missing required source fields are rejected before canonicalization; database failures abort the affected item.
- **Hard part:** remote listings do not share stable identifiers, so similarity matching is deliberately conservative.
- **Red tests:** `test_two_sources_create_one_event_and_one_new_alert`, `test_deadline_change_is_material_not_a_second_new_event`, `test_preferences_queue_and_owner_actions_persist`, `test_bookmarks_can_be_added_listed_removed_and_reloaded`, and `test_source_health_warns_once_after_error_streak`.

## alert planner and URL verifier

- **Owns:** owner filters, pause/digest state, quiet-hour delivery times, stable New/Change/72h/24h alert keys, daily digest keys, and live URL checks.
- **Promises:** muted events/sources/domains never alert, including alerts queued before the owner changed a control; preferences are explainable; quiet hours queue until 06:30 WAT; dead canonical URLs are suppressed (R-CONTROL-1/R-URL-1/R-DIGEST-1).
- **Depends on:** canonical events, owner preferences, WAT timezone data, and bounded HTTP HEAD/GET calls.
- **Fails how:** unknown values do not invent facts; HTTP errors resolve to `False`; a failed delivery remains unrecorded for retry.
- **Hard part:** URL availability can change after verification and some valid providers reject HEAD, hence GET fallback.
- **Red tests:** `test_dead_url_is_suppressed_before_alert`, `test_quiet_hours_queue_instead_of_sending`, `test_saved_pause_preference_is_reloaded_before_each_cycle`, and URL verifier fallback tests.

## database

- **Owns:** SQLite `seen` and `source_state` tables.
- **Promises:** unique notification ids; source URLs for clickable archive results; additive migration of legacy `seen` tables; WAL mode and a busy timeout; source baseline state survives restarts.
- **Depends on:** a writable local or mounted filesystem.
- **Fails how:** database errors abort the current item instead of risking an untracked send.
- **Hard part:** preserving the archive across cloud redeployments.
- **Red tests:** unique-id and persistence tests -> R-DEDUP-1/R-BOOTSTRAP-1; `test_database_migrates_legacy_seen_table_for_clickable_archive` -> R-ARCHIVE-1.

## Telegram delivery

- **Owns:** Telegram message formatting and outbound `sendMessage` calls.
- **Promises:** messages stay within Telegram's 4,096-character limit; canonical alerts are seven-line HTML cards with WAT provenance and Open/Mute/Bookmark actions; ongoing events fit in one bounded digest; inferred tags are labelled; credentials are not logged (R-SECRET-1).
- **Depends on:** Telegram Bot API; a valid bot token and private chat id.
- **Fails how:** retryable network/429/5xx failures receive up to three attempts; permanent 4xx responses fail immediately.
- **Hard part:** Markdown escaping and the send/commit crash window.
- **Red tests:** `test_send_retries_three_times_then_stops`, `test_format_message_does_not_wrap_untrusted_description_in_markdown_entity`, `test_format_message_omits_empty_fields`, and `test_format_message_shows_available_fields` -> R-DELIVERY-1; `test_format_message_uses_decision_first_premium_copy` and `test_send_hackathon_adds_one_tap_opportunity_button` -> R-PRESENTATION-1; `test_failure_logs_do_not_expose_token` -> R-SECRET-1.

## runtime deployment

- **Owns:** `.venv`, `deploy/hackathon-radar.service`, backup service/timer templates, logrotate/watchdog templates, process restart policy, and explicit `.env` loading for manual runs.
- **Promises:** manual and systemd execution use the same dependency set; when the project `.env` exists, its Telegram token/chat id override ambient agent values; production restarts after process failure (R-RUNTIME-1); credentials remain outside git (R-SECRET-1).
- **Depends on:** Python 3.11+, systemd, a readable mode-600 `.env`, network availability, and the repository path remaining `/home/ubuntu/my-bot`.
- **Fails how:** a missing virtualenv dependency fails before startup; systemd records the traceback and retries after ten seconds.
- **Hard part:** preventing interpreter drift between shell smoke tests and the live service.
- **Red tests:** `test_settings_uses_project_telegram_token_over_ambient`, `test_systemd_unit_uses_project_virtualenv_and_environment_file`, and `test_backup_timer_uses_verified_snapshot_cli` -> R-RUNTIME-1/R-SECRET-1/R-BACKUP-1.

## database backup and restore

- **Owns:** consistent SQLite snapshot creation, integrity checks, atomic publication, guarded replacement, and pre-restore recovery copies.
- **Promises:** backup can read a WAL database while the worker runs; an existing snapshot is never overwritten; temporary snapshot sidecars are removed; restore requires explicit replacement and checks for WAL/SHM sidecars both before and after the recovery copy (R-BACKUP-1).
- **Depends on:** Python's SQLite backup API and a writable destination on the same filesystem for atomic replacement.
- **Fails how:** missing/corrupt files, name collisions, active or newly created sidecars, or failed integrity checks abort before the destination changes.
- **Hard part:** a host restore requires pausing external restart watchdogs, stopping the live service, and verifying the original worker path after restart.
- **Red tests:** backup consistency, collision refusal, sidecar cleanup, mid-restore writer refusal, recovery-copy restore, CLI execution, and systemd timer contract tests.

## Telegram command center

- **Owns:** bot identity customization, owner-only `getUpdates`, command routing, and the native two-column reply keyboard.
- **Promises:** only the configured chat can read or mutate data; the two-column grid exposes New, Ongoing, Soon, Bookmarks, Filters, Sources, Alerts, Digest, Vault, and Hide; `/status` reports persisted cycle and source health; `/bookmarks`, `/bookmark`, and `/unbookmark` provide list/add/remove fallbacks; callbacks persist Mute and Bookmark actions; command failures do not stop APScheduler (R-COMMAND-1/R-CONTROL-1/R-STATUS-1).
- **Depends on:** Telegram Bot API long polling, legacy `Database`, `EventStore`, and active source display names.
- **Fails how:** API/network errors are logged without credentials and retried by the polling loop; unauthorized updates are silently ignored.
- **Hard part:** avoiding a second `getUpdates` consumer while keeping shutdown bounded.
- **Red tests:** `test_grid_uses_two_columns_and_persistent_keyboard`, `test_bookmark_commands_add_list_and_remove`, `test_callback_actions_are_owner_locked_and_persist`, `test_unauthorized_chat_is_ignored`, `test_grid_and_status_commands_send_owner_dashboard`, `test_fresh_finds_are_clickable_and_escape_untrusted_copy`, `test_command_outputs_stay_within_compact_line_budgets`, `test_bot_customization_registers_minimal_commands`, and `test_profile_photo_upload_uses_static_jpg_attachment` -> R-COMMAND-1/R-CONTROL-1/R-PRESENTATION-1.
