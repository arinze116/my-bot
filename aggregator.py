from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Protocol

from config import Settings
from db import Database, make_id
from models import Hackathon, normalize_hackathon
from sources import SourceSpec

LOGGER = logging.getLogger(__name__)


class Notifier(Protocol):
    def send_hackathon(self, hackathon: Hackathon) -> bool: ...

    def send_error_message(self, source: str, error: Exception) -> bool: ...


@dataclass(slots=True)
class SourceBatch:
    source: SourceSpec
    hackathons: list[Hackathon] = field(default_factory=list)
    error: Exception | None = None


@dataclass(slots=True)
class CycleReport:
    fetched: int = 0
    sent: int = 0
    skipped: int = 0
    baselined: int = 0
    delivery_failures: int = 0
    source_errors: dict[str, str] = field(default_factory=dict)


class RadarService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        notifier: Notifier,
        sources: list[SourceSpec],
        *,
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.database = database
        self.notifier = notifier
        self.sources = sources
        self.dry_run = dry_run

    def run_cycle(self) -> CycleReport:
        report = CycleReport()
        for batch in self._fetch_batches():
            if batch.error:
                self._record_source_error(report, batch)
                continue
            report.fetched += len(batch.hackathons)
            self._process_batch(batch, report)
        LOGGER.info(
            "Cycle complete: fetched=%s sent=%s skipped=%s baselined=%s source_errors=%s",
            report.fetched,
            report.sent,
            report.skipped,
            report.baselined,
            len(report.source_errors),
        )
        return report

    def _fetch_batches(self) -> list[SourceBatch]:
        if not self.sources:
            return []
        workers = min(8, len(self.sources))
        batches: dict[str, SourceBatch] = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as executor:
            futures = {executor.submit(source.fetch): source for source in self.sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    hackathons = [normalize_hackathon(item) for item in future.result()]
                    batches[source.name] = SourceBatch(source, _deduplicate(hackathons))
                except Exception as error:  # source isolation boundary
                    batches[source.name] = SourceBatch(source, error=error)
        return [batches[source.name] for source in self.sources]

    def _process_batch(self, batch: SourceBatch, report: CycleReport) -> None:
        is_initialized = self.database.is_source_initialized(batch.source.name)
        if not is_initialized and self.settings.bootstrap_mode == "baseline" and not self.dry_run:
            report.baselined += self.database.mark_many_seen(batch.hackathons)
            self.database.mark_source_initialized(batch.source.name)
            return
        for hackathon in batch.hackathons:
            self._process_hackathon(hackathon, report)
        if not self.dry_run:
            self.database.mark_source_initialized(batch.source.name)

    def _process_hackathon(self, hackathon: Hackathon, report: CycleReport) -> None:
        uid = make_id(hackathon["title"], hackathon["url"])
        if self.database.is_seen(uid):
            report.skipped += 1
            return
        try:
            was_sent = self.notifier.send_hackathon(hackathon)
        except Exception as error:  # delivery isolation boundary
            LOGGER.error("Notification formatting or delivery failed: %s", type(error).__name__)
            report.delivery_failures += 1
            return
        if not was_sent:
            report.delivery_failures += 1
            return
        report.sent += 1
        if not self.dry_run:
            self.database.mark_seen(uid, hackathon["title"], hackathon["platform"])

    def _record_source_error(self, report: CycleReport, batch: SourceBatch) -> None:
        assert batch.error is not None
        error_label = f"{type(batch.error).__name__}: {batch.error}"
        report.source_errors[batch.source.name] = error_label
        LOGGER.error("Source %s failed: %s", batch.source.name, error_label)
        if self.settings.debug_mode:
            self.notifier.send_error_message(batch.source.display_name, batch.error)


def _deduplicate(hackathons: list[Hackathon]) -> list[Hackathon]:
    unique: dict[str, Hackathon] = {}
    for hackathon in hackathons:
        uid = make_id(hackathon["title"], hackathon["url"])
        unique.setdefault(uid, hackathon)
    return list(unique.values())
