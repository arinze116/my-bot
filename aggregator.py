from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from alert_planner import (
    AlertPlan,
    AlertPlanner,
    event_matches_filters,
    preferences_from_mapping,
)
from config import Settings
from db import Database, make_id
from event_model import CanonicalEvent, canonicalize_hackathon
from event_store import EventStore, Sighting
from models import Hackathon, normalize_hackathon
from sources import SourceSpec

LOGGER = logging.getLogger(__name__)


class EmptySourceResultError(RuntimeError):
    pass


class Notifier(Protocol):
    def send_hackathon(self, hackathon: Hackathon) -> bool: ...

    def send_error_message(self, source: str, error: Exception) -> bool: ...

    def send_event(
        self,
        event: CanonicalEvent,
        *,
        alert_type: str,
        reasons: tuple[str, ...],
        changes: dict[str, tuple[str, str]],
    ) -> bool: ...

    def send_source_health(self, source: str, error_streak: int, error: str) -> bool: ...

    def send_digest(self, events: list[CanonicalEvent]) -> bool: ...


class URLResolver(Protocol):
    def is_resolvable(self, url: str) -> bool: ...


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
    queued: int = 0
    suppressed: int = 0
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
        event_store: EventStore | None = None,
        planner: AlertPlanner | None = None,
        url_verifier: URLResolver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.notifier = notifier
        self.sources = sources
        self.dry_run = dry_run
        self.event_store = event_store
        self.planner = planner
        self.url_verifier = url_verifier
        self.clock = clock or (lambda: datetime.now(UTC))

    def run_cycle(self) -> CycleReport:
        report = CycleReport()
        now = self.clock()
        if self.event_store:
            self.event_store.begin_cycle(now)
        try:
            self._run_cycle(report, now)
        except Exception as error:
            if self.event_store:
                try:
                    self.event_store.fail_cycle(
                        type(error).__name__,
                        completed_at=self.clock(),
                        fetched=report.fetched,
                        sent=report.sent,
                        source_errors=len(report.source_errors),
                        delivery_failures=report.delivery_failures,
                    )
                except Exception as status_error:
                    LOGGER.error(
                        "Cycle-status failure could not be recorded: %s",
                        type(status_error).__name__,
                    )
            raise
        if self.event_store:
            self.event_store.complete_cycle(
                fetched=report.fetched,
                sent=report.sent,
                source_errors=len(report.source_errors),
                delivery_failures=report.delivery_failures,
                completed_at=self.clock(),
            )
        return report

    def _run_cycle(self, report: CycleReport, now: datetime) -> None:
        if self.event_store and self.planner:
            self.planner.preferences = preferences_from_mapping(
                self.event_store.load_preferences()
            )
            self._flush_due_alerts(report, now)
        for batch in self._fetch_batches():
            if batch.error:
                self._record_source_error(report, batch, now)
                continue
            if not batch.hackathons and not batch.source.empty_result_is_valid:
                batch.error = EmptySourceResultError(
                    "Source returned zero items where catalog results are expected"
                )
                self._record_source_error(report, batch, now)
                continue
            report.fetched += len(batch.hackathons)
            if self.event_store:
                self.event_store.record_source_success(
                    batch.source.name,
                    len(batch.hackathons),
                    now=now,
                )
            self._process_batch(batch, report, now)
        if self.event_store and self.planner:
            self._plan_deadlines(report, now)
            self._send_ongoing_digest(report, now)
        LOGGER.info(
            "Cycle complete: fetched=%s sent=%s skipped=%s baselined=%s queued=%s "
            "suppressed=%s source_errors=%s",
            report.fetched,
            report.sent,
            report.skipped,
            report.baselined,
            report.queued,
            report.suppressed,
            len(report.source_errors),
        )

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

    def _process_batch(
        self, batch: SourceBatch, report: CycleReport, now: datetime
    ) -> None:
        is_initialized = self.database.is_source_initialized(batch.source.name)
        if not is_initialized and self.settings.bootstrap_mode == "baseline" and not self.dry_run:
            report.baselined += self.database.mark_many_seen(batch.hackathons)
            if self.event_store:
                for hackathon in batch.hackathons:
                    self._baseline_event(hackathon, now)
            self.database.mark_source_initialized(batch.source.name)
            return
        for hackathon in batch.hackathons:
            if self.event_store and self.planner:
                self._process_event(hackathon, report, now)
            else:
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
            self.database.mark_seen(
                uid,
                hackathon["title"],
                hackathon["platform"],
                hackathon["url"],
            )

    def _record_source_error(
        self, report: CycleReport, batch: SourceBatch, now: datetime
    ) -> None:
        assert batch.error is not None
        error_label = f"{type(batch.error).__name__}: {batch.error}"
        report.source_errors[batch.source.name] = error_label
        LOGGER.error("Source %s failed: %s", batch.source.name, error_label)
        if self.event_store:
            health = self.event_store.record_source_error(
                batch.source.name,
                error_label,
                now=now,
            )
            should_warn = self.event_store.should_warn_source(
                batch.source.name, threshold=3, now=now
            )
            warning_sent = False
            if should_warn:
                try:
                    warning_sent = self.notifier.send_source_health(
                        batch.source.display_name,
                        int(health["error_streak"]),
                        error_label,
                    )
                except Exception as error:  # delivery isolation boundary
                    LOGGER.error("Source-health notification failed: %s", type(error).__name__)
            if warning_sent:
                self.event_store.mark_source_warned(batch.source.name, now=now)
        if self.settings.debug_mode:
            self.notifier.send_error_message(batch.source.display_name, batch.error)

    def _baseline_event(self, hackathon: Hackathon, now: datetime) -> None:
        assert self.event_store is not None
        event = canonicalize_hackathon(hackathon, now=now)
        result = self.event_store.upsert_event(event, _sighting(hackathon, now))
        self.event_store.record_alert(
            result.event["event_id"],
            "new",
            f"new:{result.event['event_id']}",
        )

    def _process_event(
        self, hackathon: Hackathon, report: CycleReport, now: datetime
    ) -> None:
        assert self.event_store is not None
        assert self.planner is not None
        event = canonicalize_hackathon(hackathon, now=now)
        result = self.event_store.upsert_event(event, _sighting(hackathon, now))
        legacy_uid = make_id(hackathon["title"], hackathon["url"])
        if self.database.is_seen(legacy_uid) and result.is_new:
            self.event_store.record_alert(
                result.event["event_id"],
                "new",
                f"new:{result.event['event_id']}",
            )
            report.skipped += 1
            return
        for plan in self.planner.plan_upsert(result.event, result, now=now):
            self._handle_plan(result.event, hackathon, plan, report, now)

    def _handle_plan(
        self,
        event: CanonicalEvent,
        hackathon: Hackathon | None,
        plan: AlertPlan,
        report: CycleReport,
        now: datetime,
    ) -> None:
        assert self.event_store is not None
        if self.event_store.has_alert(plan.alert_key):
            report.skipped += 1
            return
        if not self._event_allowed_now(event):
            report.suppressed += 1
            return
        if plan.deliver_at > now.astimezone(UTC):
            queued = self.event_store.queue_alert(
                alert_key=plan.alert_key,
                event_id=event["event_id"],
                alert_type=plan.alert_type,
                deliver_at=plan.deliver_at.isoformat(),
                payload={"reasons": list(plan.reasons), "changes": plan.changes},
            )
            report.queued += int(queued)
            return
        if self.url_verifier and not self.url_verifier.is_resolvable(event["canonical_url"]):
            LOGGER.warning("Suppressing alert for unresolved event URL")
            report.suppressed += 1
            return
        try:
            sent = self.notifier.send_event(
                event,
                alert_type=plan.alert_type,
                reasons=plan.reasons,
                changes=plan.changes,
            )
        except Exception as error:  # delivery isolation boundary
            LOGGER.error("Canonical notification failed: %s", type(error).__name__)
            report.delivery_failures += 1
            return
        if not sent:
            report.delivery_failures += 1
            return
        if self.event_store.record_alert(event["event_id"], plan.alert_type, plan.alert_key):
            report.sent += 1
        if hackathon and not self.dry_run:
            self.database.mark_seen(
                make_id(hackathon["title"], hackathon["url"]),
                hackathon["title"],
                hackathon["platform"],
                hackathon["url"],
            )

    def _flush_due_alerts(self, report: CycleReport, now: datetime) -> None:
        assert self.event_store is not None
        assert self.planner is not None
        if self.planner.preferences.paused:
            return
        for queued in self.event_store.list_due_alerts(now=now):
            event = self.event_store.get_event(queued["event_id"])
            if not self._event_allowed_now(event):
                self.event_store.remove_queued_alert(str(queued["alert_key"]))
                report.suppressed += 1
                continue
            if queued["alert_type"] == "deadline_soon" and self.event_store.was_recently_alerted(
                event["event_id"], since=now - timedelta(hours=24)
            ):
                self.event_store.remove_queued_alert(str(queued["alert_key"]))
                continue
            plan = AlertPlan(
                str(queued["alert_type"]),
                str(queued["alert_key"]),
                now,
                reasons=tuple(queued["payload"].get("reasons", ())),
                changes=dict(queued["payload"].get("changes", {})),
            )
            before = report.sent
            self._handle_plan(event, None, plan, report, now)
            if report.sent > before or self.event_store.has_alert(plan.alert_key):
                self.event_store.remove_queued_alert(plan.alert_key)

    def _event_allowed_now(self, event: CanonicalEvent) -> bool:
        assert self.event_store is not None
        assert self.planner is not None
        if self.event_store.get_event_state(event["event_id"])["muted"]:
            return False
        return event_matches_filters(event, self.planner.preferences).matches

    def _plan_deadlines(self, report: CycleReport, now: datetime) -> None:
        assert self.event_store is not None
        assert self.planner is not None
        for event in self.event_store.list_soon(now=now, hours=72):
            if self.event_store.was_recently_alerted(
                event["event_id"], since=now - timedelta(hours=24)
            ):
                continue
            plan = self.planner.plan_deadline(event, now=now)
            if plan:
                self._handle_plan(event, None, plan, report, now)

    def _send_ongoing_digest(self, report: CycleReport, now: datetime) -> None:
        assert self.event_store is not None
        assert self.planner is not None
        alert_key = self.planner.ongoing_digest_key(now=now)
        if not alert_key or self.event_store.has_alert(alert_key):
            return
        events = [
            event
            for event in self.event_store.list_ongoing(now=now, limit=10)
            if event_matches_filters(event, self.planner.preferences).matches
            and not self.event_store.was_recently_alerted(
                event["event_id"], since=now - timedelta(hours=24)
            )
            and (
                self.url_verifier is None
                or self.url_verifier.is_resolvable(event["canonical_url"])
            )
        ]
        if not events:
            return
        try:
            sent = self.notifier.send_digest(events)
        except Exception as error:  # delivery isolation boundary
            LOGGER.error("Ongoing digest failed: %s", type(error).__name__)
            report.delivery_failures += 1
            return
        if not sent:
            report.delivery_failures += 1
            return
        if self.event_store.record_alert(events[0]["event_id"], "ongoing_digest", alert_key):
            report.sent += 1


def _deduplicate(hackathons: list[Hackathon]) -> list[Hackathon]:
    unique: dict[str, Hackathon] = {}
    for hackathon in hackathons:
        uid = make_id(hackathon["title"], hackathon["url"])
        unique.setdefault(uid, hackathon)
    return list(unique.values())


def _sighting(hackathon: Hackathon, now: datetime) -> Sighting:
    return Sighting(
        hackathon["platform"],
        hackathon["url"],
        now.astimezone(UTC).isoformat(),
    )
