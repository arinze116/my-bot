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
