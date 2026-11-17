from __future__ import annotations

from bot import ConsoleNotifier
from config import Settings
from db import Database
from main import build_runtime


def test_production_runtime_wires_canonical_pipeline(settings_factory) -> None:
    settings: Settings = settings_factory()
    database = Database(settings.database_path)
    database.init()

    runtime = build_runtime(settings, database, ConsoleNotifier(), [], dry_run=False)

    assert runtime.event_store is not None
    assert runtime.url_verifier is not None
    assert runtime.service.event_store is runtime.event_store
    assert runtime.service.planner is not None
    runtime.close()


def test_dry_run_runtime_keeps_legacy_non_mutating_pipeline(settings_factory) -> None:
    settings: Settings = settings_factory()
    database = Database(settings.database_path)
    database.init()

    runtime = build_runtime(settings, database, ConsoleNotifier(), [], dry_run=True)

    assert runtime.event_store is None
    assert runtime.url_verifier is None
    assert runtime.service.event_store is None
    runtime.close()
