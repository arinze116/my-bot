from __future__ import annotations

import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from offsite_backup import (
    RecoveryVerificationError,
    RemoteDocument,
    TelegramDocumentStore,
    TelegramMessageMissingError,
    TelegramOffsiteError,
    load_catalog,
    run_offsite_backup,
)


class MemoryOffsiteStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.messages: dict[int, str] = {}
        self.deleted_messages: list[int] = []
        self.next_message_id = 1
        self.corrupt_download = False
        self.corrupt_download_numbers: set[int] = set()
        self.download_count = 0
        self.missing_messages: set[int] = set()

    def upload(self, path: Path, caption: str) -> RemoteDocument:
        message_id = self.next_message_id
        self.next_message_id += 1
        file_id = f"file-{message_id}"
        payload = path.read_bytes()
        self.files[file_id] = payload
        self.messages[message_id] = file_id
        return RemoteDocument(message_id, file_id, f"unique-{message_id}", len(payload))

    def replace(
        self,
        message_id: int,
        document: RemoteDocument,
        caption: str,
    ) -> RemoteDocument:
        if message_id in self.missing_messages:
            raise TelegramMessageMissingError("missing")
        if message_id not in self.messages:
            raise KeyError(message_id)
        self.messages[message_id] = document.file_id
        return RemoteDocument(
            message_id,
            document.file_id,
            f"stable-{document.file_id}",
            len(self.files[document.file_id]),
        )

    def download(self, file_id: str, destination: Path) -> Path:
        self.download_count += 1
        payload = self.files[file_id]
        corrupt = self.corrupt_download or self.download_count in self.corrupt_download_numbers
        destination.write_bytes(b"corrupt" if corrupt else payload)
        return destination

    def delete(self, message_id: int) -> None:
        self.messages.pop(message_id, None)
        self.deleted_messages.append(message_id)


def _write_value(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT NOT NULL)")
        connection.execute("DELETE FROM sample")
        connection.execute("INSERT INTO sample (value) VALUES (?)", (value,))


def _read_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM sample").fetchone()
    return str(row[0])


def test_offsite_backup_keeps_one_verified_message_and_restores_latest(tmp_path) -> None:
    database = tmp_path / "radar.db"
    catalog_path = tmp_path / "offsite-catalog.json"
    store = MemoryOffsiteStore()
    _write_value(database, "first")

    first = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 18, 23, tzinfo=UTC),
    )

    assert first.recovery_verified is True
    assert first.stable_message_id == 1
    assert store.deleted_messages == []
    assert stat.S_IMODE(catalog_path.stat().st_mode) == 0o600

    _write_value(database, "second")
    second = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 19, 23, tzinfo=UTC),
    )

    assert second.recovery_verified is True
    assert second.stable_message_id == 1
    assert store.deleted_messages == [2]
    assert store.messages == {1: second.file_id}
    catalog = load_catalog(catalog_path)
    assert catalog.stable is not None
    assert catalog.stable.message_id == 1
    assert catalog.stable.sha256 == second.sha256
    restored = store.download(catalog.stable.file_id, tmp_path / "latest.sqlite3")
    assert _read_value(restored) == "second"


def test_failed_recovery_drill_does_not_replace_stable_backup(tmp_path) -> None:
    database = tmp_path / "radar.db"
    catalog_path = tmp_path / "offsite-catalog.json"
    store = MemoryOffsiteStore()
    _write_value(database, "stable")
    original = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 18, 23, tzinfo=UTC),
    )
    _write_value(database, "corrupt-candidate")
    store.corrupt_download = True

    with pytest.raises(RecoveryVerificationError):
        run_offsite_backup(
            database,
            catalog_path,
            store,
            now=datetime(2026, 11, 19, 23, tzinfo=UTC),
        )

    catalog = load_catalog(catalog_path)
    assert catalog.stable is not None
    assert catalog.stable.message_id == original.stable_message_id
    assert store.messages == {original.stable_message_id: original.file_id}
    assert store.deleted_messages == [2]


def test_missing_stable_message_promotes_verified_candidate(tmp_path) -> None:
    database = tmp_path / "radar.db"
    catalog_path = tmp_path / "offsite-catalog.json"
    store = MemoryOffsiteStore()
    _write_value(database, "first")
    first = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 18, 23, tzinfo=UTC),
    )
    store.messages.pop(first.stable_message_id)
    store.missing_messages.add(first.stable_message_id)
    _write_value(database, "second")

    second = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 19, 23, tzinfo=UTC),
    )

    assert second.stable_message_id == 2
    assert store.messages == {2: second.file_id}
    assert store.deleted_messages == []


def test_failed_final_verification_rolls_back_stable_message(tmp_path) -> None:
    database = tmp_path / "radar.db"
    catalog_path = tmp_path / "offsite-catalog.json"
    store = MemoryOffsiteStore()
    _write_value(database, "stable")
    original = run_offsite_backup(
        database,
        catalog_path,
        store,
        now=datetime(2026, 11, 18, 23, tzinfo=UTC),
    )
    _write_value(database, "candidate")
    store.corrupt_download_numbers.add(4)

    with pytest.raises(RecoveryVerificationError):
        run_offsite_backup(
            database,
            catalog_path,
            store,
            now=datetime(2026, 11, 19, 23, tzinfo=UTC),
        )

    catalog = load_catalog(catalog_path)
    assert catalog.stable is not None
    assert catalog.stable.file_id == original.file_id
    assert store.messages == {original.stable_message_id: original.file_id}
    assert store.deleted_messages == [2]


def test_telegram_document_store_uses_upload_download_edit_and_delete(
    settings_factory,
    tmp_path,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        if method == "sendDocument":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 7,
                        "document": {
                            "file_id": "candidate-file",
                            "file_unique_id": "candidate-unique",
                            "file_size": 8,
                        },
                    },
                },
            )
        if method == "getFile":
            return httpx.Response(
                200,
                json={"ok": True, "result": {"file_path": "documents/backup.sqlite3"}},
            )
        if request.url.path.endswith("documents/backup.sqlite3"):
            return httpx.Response(200, content=b"database")
        if method == "editMessageMedia":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 5,
                        "document": {
                            "file_id": "stable-file",
                            "file_unique_id": "stable-unique",
                            "file_size": 8,
                        },
                    },
                },
            )
        if method == "deleteMessage":
            return httpx.Response(200, json={"ok": True, "result": True})
        raise AssertionError(request.url)

    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"database")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = TelegramDocumentStore(settings_factory(), client=client)

    uploaded = store.upload(source, "candidate")
    downloaded = store.download(uploaded.file_id, tmp_path / "downloaded.sqlite3")
    replaced = store.replace(5, uploaded, "verified")
    store.delete(uploaded.message_id)

    assert downloaded.read_bytes() == b"database"
    assert replaced.message_id == 5
    assert calls == [
        "sendDocument",
        "getFile",
        "backup.sqlite3",
        "editMessageMedia",
        "deleteMessage",
    ]


def test_telegram_document_store_treats_already_applied_edit_as_success(
    settings_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"ok": False, "description": "Bad Request: message is not modified"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = TelegramDocumentStore(settings_factory(), client=client)
    candidate = RemoteDocument(9, "candidate-file", "candidate-unique", 123)

    result = store.replace(5, candidate, "verified")

    assert result == RemoteDocument(5, "candidate-file", "candidate-unique", 123)


def test_telegram_offsite_network_failure_does_not_expose_token(
    settings_factory,
    tmp_path,
    caplog,
) -> None:
    settings = settings_factory(telegram_retry_attempts=1)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"database")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = TelegramDocumentStore(settings, client=client)

    with pytest.raises(TelegramOffsiteError) as captured:
        store.upload(source, "candidate")

    output = f"{captured.value}\n{caplog.text}"
    assert settings.telegram_bot_token not in output


def test_telegram_document_upload_does_not_retry_ambiguous_write(
    settings_factory,
    tmp_path,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("response lost", request=request)

    source = tmp_path / "backup.sqlite3"
    source.write_bytes(b"database")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = TelegramDocumentStore(settings_factory(), client=client, sleeper=lambda _: None)

    with pytest.raises(TelegramOffsiteError):
        store.upload(source, "candidate")

    assert attempts == 1
