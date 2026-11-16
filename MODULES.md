# MODULES.md — module contracts

## source adapters

- **Owns:** no persistent state; one provider contract per `scrapers/<source>.py`.
- **Promises:** `fetch() -> list[dict]`; required `title`, `url`, and `platform` values are non-empty; outside calls obey R-TIMEOUT-1; remote fields are treated as untrusted; X results pass `is_announcement()` and obey R-DISCOVERY-1.
- **Depends on:** public provider pages/APIs, whose availability and schemas have no common SLA.
- **Fails how:** raises a source-scoped exception; the orchestrator logs it and continues other sources.
- **Hard part:** detecting provider contract drift without creating false alerts.
- **Red tests:** `test_http_client_uses_bounded_timeouts` -> R-TIMEOUT-1; `test_is_announcement_rejects_recap`, `test_is_announcement_accepts_listing`, and `test_twitter_fetch_filters_requested_noise` -> R-DISCOVERY-1; parser fixture tests -> source contracts.

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
- **Promises:** messages stay within Telegram's 4,096-character limit; empty optional fields are omitted; untrusted descriptions cannot create an unterminated Markdown entity; credentials are not logged (R-SECRET-1); retry count is bounded (R-DELIVERY-1).
- **Depends on:** Telegram Bot API; a valid bot token and private chat id.
- **Fails how:** retryable network/429/5xx failures receive up to three attempts; permanent 4xx responses fail immediately.
- **Hard part:** Markdown escaping and the send/commit crash window.
- **Red tests:** `test_send_retries_three_times_then_stops`, `test_format_message_does_not_wrap_untrusted_description_in_markdown_entity`, `test_format_message_omits_empty_fields`, and `test_format_message_shows_available_fields` -> R-DELIVERY-1; `test_failure_logs_do_not_expose_token` -> R-SECRET-1.

## runtime deployment

- **Owns:** `.venv`, `deploy/hackathon-radar.service`, logrotate/watchdog templates, process restart policy, and explicit `.env` loading for manual runs.
- **Promises:** manual and systemd execution use the same dependency set; when the project `.env` exists, its Telegram token/chat id override ambient agent values; production restarts after process failure (R-RUNTIME-1); credentials remain outside git (R-SECRET-1).
- **Depends on:** Python 3.11+, systemd, a readable mode-600 `.env`, network availability, and the repository path remaining `/home/ubuntu/my-bot`.
- **Fails how:** a missing virtualenv dependency fails before startup; systemd records the traceback and retries after ten seconds.
- **Hard part:** preventing interpreter drift between shell smoke tests and the live service.
- **Red tests:** `test_settings_uses_project_telegram_token_over_ambient` and `test_systemd_unit_uses_project_virtualenv_and_environment_file` -> R-RUNTIME-1/R-SECRET-1.
