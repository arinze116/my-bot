from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

import httpx

from config import Settings
from database_backup import backup_database, restore_database

LOGGER = logging.getLogger(__name__)
MAX_TELEGRAM_DOWNLOAD_BYTES = 20 * 1024 * 1024
CATALOG_VERSION = 1


class RecoveryVerificationError(RuntimeError):
    pass


class OffsiteBackupRunningError(RuntimeError):
    pass


class TelegramOffsiteError(RuntimeError):
    pass


class TelegramMessageMissingError(TelegramOffsiteError):
    pass


@dataclass(frozen=True, slots=True)
class RemoteDocument:
    message_id: int
    file_id: str
    file_unique_id: str
    size: int


@dataclass(frozen=True, slots=True)
class OffsiteBackupRecord:
    message_id: int
    file_id: str
    file_unique_id: str
    filename: str
    created_at: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class BackupCatalog:
    stable: OffsiteBackupRecord | None = None
    pending_deletions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class OffsiteRunResult:
    stable_message_id: int
    file_id: str
    sha256: str
    size: int
    recovery_verified: bool
    deleted_messages: tuple[int, ...]


class OffsiteStore(Protocol):
    def upload(self, path: Path, caption: str) -> RemoteDocument: ...

    def replace(
        self,
        message_id: int,
        document: RemoteDocument,
        caption: str,
    ) -> RemoteDocument: ...

    def download(self, file_id: str, destination: Path) -> Path: ...

    def delete(self, message_id: int) -> None: ...


def run_offsite_backup(
    database_path: str | Path,
    catalog_path: str | Path,
    store: OffsiteStore,
    *,
    now: datetime | None = None,
    temporary_parent: str | Path | None = None,
) -> OffsiteRunResult:
    database = Path(database_path)
    catalog_file = Path(catalog_path)
    current = _utc(now)
    with _catalog_lock(catalog_file):
        catalog = load_catalog(catalog_file)
        catalog, deleted = _delete_pending(catalog, store)
        if deleted:
            save_catalog(catalog_file, catalog)
        with tempfile.TemporaryDirectory(
            prefix="hackathon-radar-offsite-",
            dir=temporary_parent,
        ) as temporary_name:
            temporary = Path(temporary_name)
            snapshot = backup_database(
                database,
                temporary,
                now=current,
                prefix="hackathon-radar-offsite",
            )
            digest = _sha256(snapshot)
            size = snapshot.stat().st_size
            if size > MAX_TELEGRAM_DOWNLOAD_BYTES:
                raise ValueError("Snapshot exceeds Telegram's verified download limit")
            candidate = store.upload(snapshot, _candidate_caption(snapshot.name, digest))
            stable_replaced = False
            try:
                _verify_remote(store, candidate.file_id, digest, temporary)
                stable_message_id = (
                    catalog.stable.message_id if catalog.stable else candidate.message_id
                )
                stable_replaced = catalog.stable is not None
                try:
                    stable_document = store.replace(
                        stable_message_id,
                        candidate,
                        _verified_caption(snapshot.name, digest, current),
                    )
                except TelegramMessageMissingError:
                    stable_replaced = False
                    stable_document = store.replace(
                        candidate.message_id,
                        candidate,
                        _verified_caption(snapshot.name, digest, current),
                    )
                _verify_remote(store, stable_document.file_id, digest, temporary)
            except Exception:
                rollback_error = _rollback(catalog.stable, store) if stable_replaced else None
                catalog = _delete_or_queue(catalog, candidate.message_id, store)
                save_catalog(catalog_file, catalog)
                if rollback_error is not None:
                    raise RecoveryVerificationError(
                        "Could not restore the previous off-site backup"
                    ) from rollback_error
                raise

            record = OffsiteBackupRecord(
                message_id=stable_document.message_id,
                file_id=stable_document.file_id,
                file_unique_id=stable_document.file_unique_id,
                filename=snapshot.name,
                created_at=current.isoformat(),
                sha256=digest,
                size=size,
            )
            pending = catalog.pending_deletions
            if candidate.message_id != stable_document.message_id:
                pending = (*pending, candidate.message_id)
            catalog = BackupCatalog(record, pending)
            save_catalog(catalog_file, catalog)
            catalog, newly_deleted = _delete_pending(catalog, store)
            save_catalog(catalog_file, catalog)
            return OffsiteRunResult(
                stable_message_id=record.message_id,
                file_id=record.file_id,
                sha256=record.sha256,
                size=record.size,
                recovery_verified=True,
                deleted_messages=(*deleted, *newly_deleted),
            )


def load_catalog(path: str | Path) -> BackupCatalog:
    catalog_path = Path(path)
    if not catalog_path.exists():
        return BackupCatalog()
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != CATALOG_VERSION:
        raise ValueError("Unsupported off-site backup catalog")
    stable_raw = raw.get("stable")
    stable = None
    if stable_raw is not None:
        if not isinstance(stable_raw, dict):
            raise ValueError("Invalid stable backup record")
        stable = OffsiteBackupRecord(
            message_id=_positive_int(stable_raw, "message_id"),
            file_id=_required_text(stable_raw, "file_id"),
            file_unique_id=_required_text(stable_raw, "file_unique_id"),
            filename=_required_text(stable_raw, "filename"),
            created_at=_required_text(stable_raw, "created_at"),
            sha256=_required_text(stable_raw, "sha256"),
            size=_positive_int(stable_raw, "size"),
        )
    pending_raw = raw.get("pending_deletions", [])
    if not isinstance(pending_raw, list):
        raise ValueError("Invalid pending deletion list")
    pending = tuple(int(item) for item in pending_raw if int(item) > 0)
    return BackupCatalog(stable, pending)


def save_catalog(path: str | Path, catalog: BackupCatalog) -> None:
    catalog_path = Path(path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{catalog_path.name}.",
        suffix=".tmp",
        dir=catalog_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": CATALOG_VERSION,
                    "stable": asdict(catalog.stable) if catalog.stable else None,
                    "pending_deletions": list(catalog.pending_deletions),
                },
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, catalog_path)
        catalog_path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


class TelegramDocumentStore:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        settings.validate_telegram()
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=_timeout(settings.http_timeout_seconds))
        self.sleeper = sleeper
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    def upload(self, path: Path, caption: str) -> RemoteDocument:
        try:
            with path.open("rb") as document:
                response = self.client.post(
                    self._api_url("sendDocument"),
                    data={
                        "chat_id": self.settings.telegram_chat_id,
                        "caption": caption,
                        "disable_notification": "true",
                    },
                    files={
                        "document": (
                            path.name,
                            document,
                            "application/vnd.sqlite3",
                        )
                    },
                )
        except httpx.HTTPError as error:
            LOGGER.warning(
                "Telegram off-site upload attempt failed: %s",
                type(error).__name__,
            )
            raise TelegramOffsiteError("Telegram document upload failed") from None
        return _remote_document(_result(response, "sendDocument"))

    def replace(
        self,
        message_id: int,
        document: RemoteDocument,
        caption: str,
    ) -> RemoteDocument:
        not_modified_result = {
            "message_id": message_id,
            "document": {
                "file_id": document.file_id,
                "file_unique_id": document.file_unique_id,
                "file_size": document.size,
            },
        }
        result = self._post_json(
            "editMessageMedia",
            {
                "chat_id": self.settings.telegram_chat_id,
                "message_id": message_id,
                "media": {
                    "type": "document",
                    "media": document.file_id,
                    "caption": caption,
                },
            },
            not_modified_result=not_modified_result,
        )
        if not isinstance(result, dict):
            raise TelegramOffsiteError("Telegram editMessageMedia returned no message")
        return _remote_document(result)

    def download(self, file_id: str, destination: Path) -> Path:
        result = self._post_json("getFile", {"file_id": file_id})
        if not isinstance(result, dict):
            raise TelegramOffsiteError("Telegram getFile returned no file")
        file_path = _required_text(result, "file_path")
        pure_path = PurePosixPath(file_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise TelegramOffsiteError("Telegram returned an invalid file path")
        response = self._get_file(file_path)
        if len(response.content) > MAX_TELEGRAM_DOWNLOAD_BYTES:
            raise TelegramOffsiteError("Telegram download exceeded the verified size limit")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(response.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def delete(self, message_id: int) -> None:
        result = self._post_json(
            "deleteMessage",
            {"chat_id": self.settings.telegram_chat_id, "message_id": message_id},
            missing_is_success=True,
        )
        if result is not True:
            raise TelegramOffsiteError("Telegram deleteMessage returned false")

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _post_json(
        self,
        method: str,
        payload: dict[str, object],
        *,
        missing_is_success: bool = False,
        not_modified_result: object | None = None,
    ) -> object:
        for attempt in range(1, self.settings.telegram_retry_attempts + 1):
            try:
                response = self.client.post(self._api_url(method), json=payload)
            except httpx.HTTPError as error:
                if not self._retry(attempt, error):
                    raise TelegramOffsiteError(f"Telegram {method} failed") from None
                continue
            if missing_is_success and _is_missing_message(response):
                return True
            if not_modified_result is not None and _is_not_modified(response):
                return not_modified_result
            if method == "editMessageMedia" and _is_missing_edit(response):
                raise TelegramMessageMissingError("Telegram stable backup message is missing")
            if self._retryable_response(response) and self._wait_for_retry(attempt):
                continue
            return _result(response, method)
        raise TelegramOffsiteError(f"Telegram {method} failed")

    def _get_file(self, file_path: str) -> httpx.Response:
        for attempt in range(1, self.settings.telegram_retry_attempts + 1):
            try:
                response = self.client.get(self._file_url(file_path))
            except httpx.HTTPError as error:
                if not self._retry(attempt, error):
                    raise TelegramOffsiteError("Telegram file download failed") from None
                continue
            if self._retryable_response(response) and self._wait_for_retry(attempt):
                continue
            if response.status_code != 200:
                raise TelegramOffsiteError(
                    f"Telegram file download failed with HTTP {response.status_code}"
                )
            return response
        raise TelegramOffsiteError("Telegram file download failed")

    def _retry(self, attempt: int, error: Exception) -> bool:
        LOGGER.warning("Telegram off-site network attempt failed: %s", type(error).__name__)
        return self._wait_for_retry(attempt)

    def _wait_for_retry(self, attempt: int) -> bool:
        if attempt >= self.settings.telegram_retry_attempts:
            return False
        self.sleeper(self.settings.telegram_retry_delay_seconds)
        return True

    @staticmethod
    def _retryable_response(response: httpx.Response) -> bool:
        return response.status_code == 429 or response.status_code >= 500

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/{method}"

    def _file_url(self, file_path: str) -> str:
        return f"https://api.telegram.org/file/bot{self.settings.telegram_bot_token}/{file_path}"


def _verify_remote(
    store: OffsiteStore,
    file_id: str,
    expected_sha256: str,
    directory: Path,
) -> None:
    downloaded = store.download(file_id, directory / "downloaded.sqlite3")
    if _sha256(downloaded) != expected_sha256:
        raise RecoveryVerificationError("Downloaded off-site snapshot hash mismatch")
    restored = directory / "restored.sqlite3"
    restored.unlink(missing_ok=True)
    restore_database(downloaded, restored)
    if _sha256(restored) != expected_sha256:
        raise RecoveryVerificationError("Restored off-site snapshot hash mismatch")


def _rollback(
    record: OffsiteBackupRecord | None,
    store: OffsiteStore,
) -> Exception | None:
    if record is None:
        return None
    try:
        store.replace(
            record.message_id,
            RemoteDocument(
                record.message_id,
                record.file_id,
                record.file_unique_id,
                record.size,
            ),
            _verified_caption(
                record.filename,
                record.sha256,
                datetime.fromisoformat(record.created_at),
            ),
        )
    except Exception as error:
        return error
    return None


def _delete_or_queue(
    catalog: BackupCatalog,
    message_id: int,
    store: OffsiteStore,
) -> BackupCatalog:
    try:
        store.delete(message_id)
    except Exception:
        return BackupCatalog(catalog.stable, (*catalog.pending_deletions, message_id))
    return catalog


def _delete_pending(
    catalog: BackupCatalog,
    store: OffsiteStore,
) -> tuple[BackupCatalog, tuple[int, ...]]:
    deleted: list[int] = []
    remaining: list[int] = []
    for message_id in catalog.pending_deletions:
        try:
            store.delete(message_id)
        except Exception:
            remaining.append(message_id)
        else:
            deleted.append(message_id)
    if remaining:
        raise TelegramOffsiteError("Could not enforce off-site backup retention")
    return BackupCatalog(catalog.stable, ()), tuple(deleted)


@contextmanager
def _catalog_lock(path: Path):
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OffsiteBackupRunningError("Another off-site backup is running") from error
        yield


def _result(response: httpx.Response, method: str) -> object:
    try:
        payload = response.json()
    except ValueError as error:
        raise TelegramOffsiteError(f"Telegram {method} returned invalid JSON") from error
    if (
        response.status_code != 200
        or not isinstance(payload, dict)
        or payload.get("ok") is not True
    ):
        raise TelegramOffsiteError(f"Telegram {method} failed with HTTP {response.status_code}")
    return payload.get("result")


def _remote_document(message: Mapping[str, object]) -> RemoteDocument:
    document = message.get("document")
    if not isinstance(document, Mapping):
        raise TelegramOffsiteError("Telegram response did not include a document")
    return RemoteDocument(
        message_id=_positive_int(message, "message_id"),
        file_id=_required_text(document, "file_id"),
        file_unique_id=_required_text(document, "file_unique_id"),
        size=_positive_int(document, "file_size"),
    )


def _is_missing_message(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and "message to delete not found" in str(
        payload.get("description", "")
    ).casefold()


def _is_missing_edit(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and "message to edit not found" in str(
        payload.get("description", "")
    ).casefold()


def _is_not_modified(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and "message is not modified" in str(
        payload.get("description", "")
    ).casefold()


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required field: {key}")
    return value


def _positive_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Invalid positive integer: {key}")
    parsed = int(value) if isinstance(value, (int, str)) else 0
    if parsed <= 0:
        raise ValueError(f"Invalid positive integer: {key}")
    return parsed


def _candidate_caption(filename: str, digest: str) -> str:
    return (
        "Hackathon Radar off-host backup candidate\n"
        f"File: {filename}\n"
        f"SHA-256: {digest}\n"
        "Recovery verification in progress."
    )


def _verified_caption(filename: str, digest: str, created_at: datetime) -> str:
    return (
        "Hackathon Radar latest verified off-host backup\n"
        f"UTC: {_utc(created_at).isoformat()}\n"
        f"File: {filename}\n"
        f"SHA-256: {digest}\n"
        "Download and SQLite restore drill passed."
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds, connect=seconds, read=seconds, write=seconds, pool=seconds)
