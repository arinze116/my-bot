# RED/GREEN evidence — 2026-11-16

## 2026-11-18 reliability tranche

### R-CONTROL-1 — queued alerts recheck current owner controls

- RED command: `.venv/bin/python -m pytest -q tests/test_aggregator.py::test_due_queue_is_discarded_after_event_is_muted`.
- RED excerpt: `assert report.sent == 0` failed because the queued alert was sent and `report.sent` was `1`.
- GREEN behavior: the service checks current event mute state and current filters, removes ineligible queued alerts, and records one suppression.

### R-HEALTH-1 — unexpected empty catalogs are degraded

- RED command: the two empty-source tests in `tests/test_aggregator.py`.
- RED excerpts: the catalog `error_streak` was `0`, expected `3`; `SourceSpec` rejected the explicit `empty_result_is_valid` contract.
- GREEN behavior: catalog sources treat zero items as a source failure; Lablab, HackerEarth, Gitcoin, X, and any explicitly marked source may return zero as healthy.

### R-STATUS-1 — persisted polling outcome

- RED command: the cycle-status aggregator and Telegram status tests.
- RED excerpts: `EventStore` had no `get_runtime_status` or `begin_cycle` methods.
- Review RED excerpt: `RuntimeStatus` had no `delivery_failures` field and `complete_cycle` rejected
  the new delivery-failure count.
- GREEN behavior: the latest cycle start, completion, outcome, counts, delivery failures, and fatal
  error type persist in `runtime_status`; `/status` renders the stored result and current source
  health.

### Prize normalization — shorthand verified USD amounts

- RED command: `.venv/bin/python -m pytest -q tests/test_event_model.py::test_prize_parser_handles_usd_suffixes_and_words`.
- RED excerpt: `$50K` parsed as `50`, expected `50000`.
- GREEN behavior: verified USD text supports `K`, `M`, `B`, `thousand`, `million`, and `billion`; non-USD text remains unknown.

### R-BACKUP-1 — consistent backup and guarded restore

- RED commands: `tests/test_database_backup.py` and `tests/test_deployment.py::test_backup_timer_uses_verified_snapshot_cli`.
- RED excerpts: `ModuleNotFoundError: No module named 'database_backup'`; the backup systemd unit did not exist.
- GREEN behavior: online SQLite snapshots pass integrity checks and collision refusal; restore requires explicit replacement, preserves a recovery snapshot, and refuses active sidecars; the CLI and inactive daily timer contract pass.

### Current-revision GREEN

- Focused safeguard command: thirteen queue, health, status, prize, source-policy, backup, CLI, and
  deployment tests.
- Focused excerpt: `13 passed`.
- Full command: `make ci`.
- Full excerpt: Ruff `All checks passed!`; pytest `100 passed`.

The faults below were temporarily injected into production code, observed by the named test, and then removed. The full current suite is recorded in `REPORT.md`.

## R-TIMEOUT-1 — `test_http_client_uses_bounded_timeouts`

- Fault: forced the shared HTTP client timeout to 60 seconds.
- RED command: `.venv/bin/python -m pytest -q tests/test_common.py::test_http_client_uses_bounded_timeouts`
- RED excerpt: `assert 60.0 <= 20` and `Timeout(timeout=60.0).connect`.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-DELIVERY-1 — `test_send_retries_three_times_then_stops`

- Fault: allowed a fourth retryable Telegram call.
- RED command: `.venv/bin/python -m pytest -q tests/test_bot.py::test_send_retries_three_times_then_stops`
- RED excerpt: `assert 4 == 3`; four HTTP 503 attempts were captured.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-SECRET-1 — `test_failure_logs_do_not_expose_token`

- Fault: logged the full token-bearing Telegram endpoint after a network error.
- RED command: selected safeguard suite.
- RED excerpt: the canary `canary-secret-token` appeared in captured logs.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed` and the canary was absent.

## R-SECRET-1 — `test_success_logs_do_not_expose_token`

- Fault: left the dependency's default INFO request logging enabled for Telegram's token-bearing URL.
- RED command: `.venv/bin/python -m pytest -q tests/test_bot.py::test_success_logs_do_not_expose_token`
- RED excerpt: `ambient-log-canary` appeared in `httpx`'s `HTTP Request: POST ...` record.
- GREEN command: the same selected test after setting `httpx` and `httpcore` to WARNING.
- GREEN excerpt: `1 passed`.

## R-BOOTSTRAP-1 — `test_baseline_marks_without_sending`

- Fault: bypassed the first-source baseline branch.
- RED command: selected safeguard suite.
- RED excerpt: `report.baselined == 0`, expected `1`; a notification was sent.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-DEDUP-1 — `test_duplicate_is_sent_once`

- Fault: bypassed the database `is_seen` check.
- RED command: selected safeguard suite.
- RED excerpt: the second cycle reported `sent == 1`, expected `0`.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-DELIVERY-1 — `test_failed_delivery_is_not_marked_seen`

- Fault: inserted the database record before attempting Telegram delivery.
- RED command: selected safeguard suite.
- RED excerpt: `database.is_seen(uid) is True`, expected `False` after a failed send.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-SCHEDULE-1 — `test_scheduler_allows_only_one_cycle_at_a_time`

- Fault: changed APScheduler `max_instances` from 1 to 2.
- RED command: selected safeguard suite.
- RED excerpt: `job.max_instances == 2`, expected `1`.
- GREEN excerpt after restoration: selected safeguard suite reported `7 passed`.

## R-RUNTIME-1 — project dotenv and systemd virtualenv

- Tests: `test_settings_loads_project_dotenv_without_overriding_environment` and
  `test_systemd_unit_uses_project_virtualenv_and_environment_file`.
- Faults: omitted the project dotenv load and omitted the version-controlled production unit.
- RED command: `.venv/bin/python -m pytest -q tests/test_config.py tests/test_deployment.py`.
- RED excerpts: `assert [] == [(expected_path, False)]` and
  `AssertionError: production systemd unit file is missing`.
- GREEN command: `.venv/bin/python -m pytest -q tests/test_config.py tests/test_deployment.py`.
- GREEN excerpt after implementation: `2 passed`.
- Full-suite GREEN command: `.venv/bin/python -m pytest`.
- Full-suite GREEN excerpt: `30 passed in 0.60s`.

## R-DISCOVERY-1 — X keyword coverage and noise rejection

- Tests: `test_default_twitter_queries_cover_requested_discovery_terms` and
  `test_twitter_fetch_filters_requested_noise`.
- Faults: retained the old three-query set and passed every X result through without applying the
  owner's noise exclusions.
- RED command: `.venv/bin/python -m pytest -q tests/test_scrapers.py::test_default_twitter_queries_cover_requested_discovery_terms tests/test_scrapers.py::test_twitter_fetch_filters_requested_noise`.
- RED excerpts: discovery coverage reported many `Extra items in the left set`; noise filtering
  reported `Left contains 5 more items`.
- GREEN command: the same two-test command after grouping terms and adding local rejection.
- GREEN excerpt: `2 passed`.
- Full-suite GREEN command: `make ci`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `32 passed in 0.62s`.

## R-DELIVERY-1 — untrusted Telegram description formatting

- Test: `test_format_message_does_not_wrap_untrusted_description_in_markdown_entity`.
- Fault: wrapped an untrusted X description in `_..._`, allowing escaped handles and a trailing URL
  to produce an unterminated legacy Markdown entity.
- RED command: `.venv/bin/python -m pytest -q tests/test_bot.py::test_format_message_does_not_wrap_untrusted_description_in_markdown_entity`.
- RED excerpt: `assert "📝 _" not in message` failed because the generated line began
  `📝 _@shipordie\\_`.
- GREEN command: the same one-test command after keeping the escaped description plain.
- GREEN excerpt: `1 passed`.
- Live GREEN: the previously problematic description shape returned
  `Problematic-description delivery confirmed: True` from Telegram.
- Full-suite GREEN command: `make ci`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `33 passed in 0.63s`.

## R-DISCOVERY-1 and R-DELIVERY-1 — quality filter and empty-field cleanup

- Tests: `test_is_announcement_rejects_recap`, `test_is_announcement_accepts_listing`,
  `test_format_message_omits_empty_fields`, and `test_format_message_shows_available_fields`.
- Faults: `is_announcement()` did not exist, and every empty optional field rendered as
  `Not listed`.
- RED command: `.venv/bin/python -m pytest -q tests/test_scrapers.py::test_is_announcement_rejects_recap tests/test_scrapers.py::test_is_announcement_accepts_listing tests/test_bot.py::test_format_message_omits_empty_fields tests/test_bot.py::test_format_message_shows_available_fields`.
- RED excerpts: both discovery tests raised `AttributeError: module 'scrapers.twitter' has no
  attribute 'is_announcement'`; the formatter assertion showed `Prize Pool: Not listed`,
  `Start Date: Not listed`, `End Date: Not listed`, and `Deadline: Not listed`.
- GREEN command: the same four-test command after implementation.
- GREEN excerpt: `4 passed`.
- Full-suite GREEN command: `.venv/bin/python -m pytest`.
- Full-suite GREEN excerpt: `37 passed in 0.61s`.
- Live refinement RED: the observed first-person text `During the Spenda hackathon, I was...`
  returned `True`; the safeguard failed with `assert True is False`.
- Live refinement GREEN: after adding the first-person phrase, the focused test reported `1 passed`
  and live X output fell to 11 announcement-oriented results from the earlier 132.

## R-RUNTIME-1 — project Telegram credential authority

- Test: `test_settings_uses_project_telegram_token_over_ambient`.
- Fault: standard dotenv loading used `override=False`, so a fake ambient Codex-agent token won over
  the token stored in the project `.env`.
- RED command: `.venv/bin/python -m pytest -q tests/test_config.py::test_settings_uses_project_telegram_token_over_ambient`.
- RED excerpt: `assert 'ambient-codex-agent-token' == 'project-bot-token'`.
- GREEN command: the same focused test after reading Telegram credentials directly from the project
  file when it exists.
- GREEN excerpt: `1 passed`.
- Full-suite GREEN command: `make ci`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `37 passed in 0.60s`.

## R-COMMAND-1 — owner-only native command grid

- Tests: `test_grid_uses_two_columns_and_persistent_keyboard`,
  `test_unauthorized_chat_is_ignored`, `test_grid_and_status_commands_send_owner_dashboard`,
  `test_bot_customization_registers_minimal_commands`, and
  `test_database_exposes_recent_items_and_source_counts`.
- Fault: no command module or database read views existed.
- RED command: `.venv/bin/python -m pytest -q tests/test_commands.py tests/test_db.py::test_database_exposes_recent_items_and_source_counts`.
- RED excerpt: `ModuleNotFoundError: No module named 'commands'` during collection.
- GREEN command: the same selected command after implementation.
- GREEN excerpt: `5 passed`.
- Full-suite GREEN command: `make ci`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `42 passed in 0.71s`.

## R-PRESENTATION-1 and R-ARCHIVE-1 — premium Telegram experience

- Tests: `test_format_message_uses_decision_first_premium_copy`,
  `test_send_hackathon_adds_one_tap_opportunity_button`,
  `test_startup_message_is_personal_and_actionable`,
  `test_grid_uses_two_columns_and_persistent_keyboard`,
  `test_grid_and_status_commands_send_owner_dashboard`,
  `test_fresh_finds_are_clickable_and_escape_untrusted_copy`,
  `test_database_exposes_recent_items_and_source_counts`, and
  `test_database_migrates_legacy_seen_table_for_clickable_archive`.
- Faults: the existing formatter used the generic `NEW HACKATHON DETECTED` layout and raw dates;
  delivery had no inline action; startup and grid copy were generic; archive rows stored no URL and
  had no migration.
- RED command: the eight focused tests above before implementation.
- RED excerpt: `8 failed`; assertions showed the old `🏆 *NEW HACKATHON DETECTED*` output, missing
  `reply_markup`, missing `bot_owner_name`, old grid labels, and
  `TypeError: Database.mark_seen() takes 4 positional arguments but 5 were given`.
- GREEN command: the same eight focused tests after implementation.
- GREEN excerpt: `8 passed`.

## R-COMMAND-1 and R-PRESENTATION-1 — official bot profile photo

- Test: `test_profile_photo_upload_uses_static_jpg_attachment`.
- Fault: `TelegramCommandPoller` had no `set_profile_photo()` path.
- RED command: `.venv/bin/python -m pytest -q tests/test_commands.py::test_profile_photo_upload_uses_static_jpg_attachment`.
- RED excerpt: `AttributeError: 'TelegramCommandPoller' object has no attribute 'set_profile_photo'`.
- GREEN command: the same focused test after implementing official multipart `setMyProfilePhoto`.
- GREEN excerpt: `1 passed`.
- Full-suite GREEN command: `.venv/bin/ruff check . && .venv/bin/python -m pytest -q`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `48 passed`.

## R-PRESENTATION-1 — uncluttered command responses

- Tests: `test_grid_and_status_commands_send_owner_dashboard`,
  `test_fresh_finds_are_clickable_and_escape_untrusted_copy`, and
  `test_command_outputs_stay_within_compact_line_budgets`.
- Faults: the command transport normalized all whitespace before sending, collapsing authored line
  breaks into one dense paragraph; the response copy also repeated emojis, explanations, and an
  `Open opportunity` label for every Fresh row.
- RED command: the three focused tests above before implementation.
- RED excerpt: `3 failed`; the grid assertion received one continuous line beginning
  `🛰️ <b>Hackathon Radar</b> Welcome back, Arinze...`, Fresh still contained
  `Open opportunity ↗`, and `/grid` exceeded its three-line budget.
- GREEN command: the same three focused tests after separating inline-title truncation from
  message-length truncation and tightening every command view.
- GREEN excerpt: `3 passed`.
- Full-suite GREEN command: `.venv/bin/ruff check . && .venv/bin/python -m pytest -q`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `49 passed`.

## R-CANONICAL-1, R-URL-1, R-CONTROL-1, and R-HEALTH-1 — canonical PRD pipeline

- Tests: canonical model/store/planner/URL suites plus cross-source aggregator integration.
- Fault: the modules and runtime contracts did not exist.
- RED excerpt: test collection stopped with `ModuleNotFoundError` for `event_model`, `event_store`,
  `alert_planner`, and `url_verifier`.
- GREEN excerpt: the first architecture slice reported `13 passed`; store extensions reported
  `2 passed`; aggregator integration reported `3 passed`.
- Limits proved: two-source merge, material change, quiet-hour queue, dead-URL suppression, source
  warning throttle, persistent preferences, mutes, interests, and command queries.

## R-PRESENTATION-1 — canonical event cards and native owner actions

- Tests: `test_event_alert_is_compact_actionable_and_provenanced`,
  `test_material_change_alert_shows_only_changed_field`, and
  `test_send_event_adds_open_mute_and_interested_actions`.
- Fault: `event_alerts.py` did not exist and `TelegramClient` had no canonical event sender.
- RED excerpt: collection failed with `ModuleNotFoundError: No module named 'event_alerts'`.
- GREEN command: `.venv/bin/python -m pytest -q tests/test_event_alerts.py tests/test_event_model.py tests/test_bot.py`.
- GREEN excerpt: `18 passed`.

## R-CONTROL-1 — owner views, controls, callbacks, and live preference reload

- Tests: `test_saved_pause_preference_is_reloaded_before_each_cycle`, expanded command-grid tests,
  canonical New/Ongoing/Soon views, filter/pause/digest persistence, and callback actions.
- Faults: the planner retained startup preferences; the poller had no `EventStore`; the old grid
  exposed only Pulse/Fresh/Vault/Coverage; callback queries were ignored.
- RED excerpt: `5 failed`; one cycle sent despite saved pause, grid rows differed, and three tests
  raised `TypeError: TelegramCommandPoller.__init__() got an unexpected keyword argument
  'event_store'`.
- GREEN command: `.venv/bin/python -m pytest -q tests/test_aggregator.py::test_saved_pause_preference_is_reloaded_before_each_cycle tests/test_commands.py`.
- GREEN excerpt: `11 passed`.

## R-RUNTIME-1 — production canonical pipeline wiring

- Tests: `test_production_runtime_wires_canonical_pipeline` and
  `test_dry_run_runtime_keeps_legacy_non_mutating_pipeline`.
- Fault: `main.py` had no runtime builder and never created the canonical store, planner, or URL
  verifier.
- RED excerpt: collection failed with `ImportError: cannot import name 'build_runtime' from 'main'`.
- GREEN excerpt: `2 passed`; the production runtime owns all three components and dry-run owns none.

## Source contract — ETHGlobal official events

- Test: `test_ethglobal_event_card_parser_keeps_hackathons_only`.
- Fault: no ETHGlobal adapter existed.
- RED excerpt: collection failed with `ImportError: cannot import name 'ethglobal' from 'scrapers'`.
- GREEN excerpt: the parser test passed and the source was added behind `ENABLE_ETHGLOBAL`.
- Research evidence: official `/events` returned public cards; guessed `/api/events` returned 404.
  Luma official client search returned 401 unsigned and was documented unavailable.

## R-DIGEST-1 — daily ongoing digest without same-day duplicate spam

- Tests: `test_ongoing_digest_is_sent_once_per_wat_day`,
  `test_send_digest_groups_ongoing_events_in_one_message`, and
  `test_new_ongoing_event_is_not_repeated_in_same_day_digest`.
- Faults: `/digest` only persisted a switch; `TelegramClient.send_digest()` did not exist; a newly
  alerted ongoing event then produced two messages in the same cycle.
- RED excerpts: `AttributeError: 'TelegramClient' object has no attribute 'send_digest'`; the
  duplicate regression showed `assert 2 == 1` for sent messages.
- GREEN excerpts: digest slice `7 passed`; same-day New/digest regressions `2 passed`.

## R-DELIVERY-1 — canonical delivery exception isolation

- Test: `test_canonical_delivery_exception_is_isolated_and_not_recorded`.
- Fault: a `ValueError` raised by canonical message delivery escaped `run_cycle()`.
- RED excerpt: traceback ended at `raise ValueError("bad canonical message")`.
- GREEN excerpt: the focused canonical delivery and digest regressions reported `3 passed`; the
  failed event retained no New alert key.

## Current-revision full gate

- Command: `make ci`.
- GREEN excerpt: Ruff `All checks passed!`; pytest `85 passed in 2.78s`.

## R-COMMAND-1 — startup does not reapply rate-limited customization

- Test: `test_start_does_not_reapply_rate_limited_bot_customization`.
- Fault: every service restart called `setMyName`, `setMyDescription`, `setMyShortDescription`, and
  `setMyCommands` again. Telegram returned HTTP 429 with a long retry window.
- RED excerpt: `assert 1 == 0` because `customize_bot()` ran during `start()`.
- GREEN excerpt: focused test `1 passed`; customization remains available through
  `.venv/bin/python -m scripts.customize_bot` as an explicit one-off operation.

## R-CONTROL-1 / R-COMMAND-1 — persistent bookmark add, list, and remove

- Tests: `test_bookmarks_can_be_added_listed_removed_and_reloaded`,
  `test_grid_uses_two_columns_and_persistent_keyboard`,
  `test_bookmark_commands_add_list_and_remove`,
  `test_callback_actions_are_owner_locked_and_persist`, and
  `test_send_event_adds_open_mute_and_bookmark_actions`.
- Fault injection: inverted the bookmark query to select unbookmarked rows, replaced the grid's
  Bookmarks button with Guide, and changed the alert label back to Interested while retaining the
  bookmark callback payload.
- RED command: `.venv/bin/python -m pytest -q` with the five focused test selectors above.
- RED excerpt: `5 failed`; persisted bookmarks reloaded as `[]`, the grid differed at row 2,
  `/bookmarks` reported `Bookmarks · 0` after add, the removal refresh incorrectly retained one
  event, and the alert payload exposed `Interested` instead of `Bookmark`.
- GREEN command: the same five focused test selectors after implementation.
- GREEN excerpt: `5 passed`.
- Owner-lock fault injection: removed the configured-chat comparison from callback handling.
- Owner-lock RED command:
  `.venv/bin/python -m pytest -q tests/test_commands.py::test_callback_actions_are_owner_locked_and_persist`.
- Owner-lock RED excerpt: `assert not True`; chat `999999` was able to submit a `bookmark:`
  callback.
- Owner-lock GREEN excerpt after restoring the guard: `1 passed`.
- Full-suite GREEN command: `make ci`.
- Full-suite GREEN excerpt: Ruff `All checks passed!`; pytest `87 passed`.
