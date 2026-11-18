# ADR-0012: Telegram off-host backup

Date: 2026-11-19
Status: accepted and deployed

## Context

Host-local snapshots and restore are verified, but loss of the VPS volume would remove both the
database and its local backups. The node has no configured object-storage CLI, remote filesystem,
or backup host. It already has one owner-only Telegram Bot API destination.

The database is about 385 KB and does not contain Telegram or X credentials. Telegram accepts bot
document uploads up to 50 MB and allows bots to download files up to 20 MB. Bot messages can be
deleted only within 48 hours, which prevents a reliable long rolling history based on deletion.

## Decision

- Keep one stable latest-verified database document in the owner Telegram chat.
- Create a fresh SQLite online snapshot for every off-host run. Never upload `.env`.
- Upload a silent candidate, download it through `getFile`, compare SHA-256, restore it into an
  isolated database, and compare the restored hash before promotion.
- Do not retry `sendDocument` after a network or server response failure because Telegram provides
  no idempotency key that can prove whether the first upload created a message.
- Promote the candidate file ID into the stable message with `editMessageMedia`. Delete the fresh
  candidate after promotion. Persist failed candidate deletions for bounded retry.
- Store only message/file identifiers, filename, timestamp, size, and SHA-256 in a mode-600 atomic
  local catalog. Serialize timer and manual runs with a file lock.
- Fail before upload when the snapshot exceeds the verified 20 MB download limit.

## Alternatives considered

An S3-compatible provider, Google Drive, Dropbox, and a remote SSH host would offer conventional
multi-version retention, but no such provider or credentials are configured on this node. A public
GitHub repository is unsuitable for a private database. Accumulating Telegram messages was rejected
because bots cannot reliably delete messages older than 48 hours.

## Consequences

- Host-volume loss has one off-host recovery point no more than one successful daily run old.
- Every successful upload also proves download and restore through the real provider.
- The owner can download the stable document from Telegram even if the VPS is unavailable.
- Telegram bot chats are cloud-stored, not end-to-end encrypted. The design has one provider and one
  retained version, so it does not replace a future encrypted multi-version object-store backup.

## Deployment verification

On 2026-11-19, revision `978973b` passed `make ci` with Ruff clean and 111 tests. The off-host
timer was installed, enabled, and scheduled through systemd. Two manual production service runs
completed against the configured owner chat. The second run reused the first stable message,
replaced its document, deleted its transient candidate, and left zero pending deletions. The local
catalog remained mode 600. Each successful service run downloaded the remote document and restored
it into an isolated SQLite database before exit.

A separate, clearly labeled synthetic alert returned success through `TelegramClient.send_hackathon`
using the project configuration. Its test URL remained absent from the SQLite `seen` archive.

## Reversal trigger

Move to encrypted object storage when an approved provider and credential boundary exist, when the
database approaches 20 MB, or when recovery requires more than one historical version.
