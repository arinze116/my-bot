# MODULES.md — module contracts

## source adapters

- **Owns:** no persistent state; one provider contract per `scrapers/<source>.py`.
- **Promises:** `fetch() -> list[dict]`; required `title`, `url`, and `platform` values are non-empty; outside calls obey R-TIMEOUT-1; remote fields are treated as untrusted.
- **Depends on:** public provider pages/APIs, whose availability and schemas have no common SLA.
- **Fails how:** raises a source-scoped exception; the orchestrator logs it and continues other sources.
- **Hard part:** detecting provider contract drift without creating false alerts.
- **Red tests:** `test_http_client_uses_bounded_timeouts` -> R-TIMEOUT-1; parser fixture tests -> source contracts.

## aggregator

- **Owns:** source execution order, within-cycle deduplication, first-sync policy, and delivery-to-database sequencing.
- **Promises:** source isolation (R-SCHEDULE-1); known ids do not send (R-DEDUP-1); safe first sync does not flood Telegram (R-BOOTSTRAP-1); only successful sends are marked seen (R-DELIVERY-1).
- **Depends on:** adapters, `Database`, and `TelegramClient`.
- **Fails how:** a source error is recorded and skipped; a delivery failure remains unseen for a later cycle.
- **Hard part:** the unavoidable ambiguity between a remote Telegram write and the local SQLite commit.
- **Red tests:** `test_failed_delivery_is_not_marked_seen` -> R-DELIVERY-1; `test_baseline_marks_without_sending` -> R-BOOTSTRAP-1; `test_duplicate_is_sent_once` -> R-DEDUP-1.

## database

- **Owns:** SQLite `seen` and `source_state` tables.
- **Promises:** unique notification ids; WAL mode and a busy timeout; source baseline state survives restarts.
- **Depends on:** a writable local or mounted filesystem.
- **Fails how:** database errors abort the current item instead of risking an untracked send.
- **Hard part:** preserving the archive across cloud redeployments.
- **Red tests:** unique-id and persistence tests -> R-DEDUP-1/R-BOOTSTRAP-1.

## Telegram delivery

- **Owns:** Telegram message formatting and outbound `sendMessage` calls.
- **Promises:** messages stay within Telegram's 4,096-character limit; credentials are not logged (R-SECRET-1); retry count is bounded (R-DELIVERY-1).
- **Depends on:** Telegram Bot API; a valid bot token and private chat id.
- **Fails how:** retryable network/429/5xx failures receive up to three attempts; permanent 4xx responses fail immediately.
- **Hard part:** Markdown escaping and the send/commit crash window.
- **Red tests:** `test_send_retries_three_times_then_stops` -> R-DELIVERY-1; `test_failure_logs_do_not_expose_token` -> R-SECRET-1.
