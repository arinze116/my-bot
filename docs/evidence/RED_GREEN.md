# RED/GREEN evidence — 2026-11-16

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
