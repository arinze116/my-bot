from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, replace

from aggregator import RadarService
from alert_planner import AlertPlanner, preferences_from_mapping
from bot import ConsoleNotifier, TelegramClient
from commands import TelegramCommandPoller
from config import Settings
from db import Database
from event_store import EventStore
from scheduler import run_scheduler
from sources import SourceSpec, enabled_sources
from url_verifier import URLVerifier

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Runtime:
    service: RadarService
    event_store: EventStore | None = None
    url_verifier: URLVerifier | None = None

    def close(self) -> None:
        if self.url_verifier is not None:
            self.url_verifier.close()


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)
    settings = Settings.from_env()
    if args.notify_existing:
        settings = replace(settings, bootstrap_mode="notify")
    if not args.dry_run:
        settings.validate_telegram()

    database = Database(settings.database_path)
    database.init()
    source_specs = enabled_sources(settings)
    notifier = ConsoleNotifier() if args.dry_run else TelegramClient(settings)
    runtime = build_runtime(
        settings,
        database,
        notifier,
        source_specs,
        dry_run=args.dry_run,
    )
    service = runtime.service
    command_poller: TelegramCommandPoller | None = None

    try:
        notifier.send_startup_message(
            database.total_seen(), [source.display_name for source in source_specs]
        )
        if args.run_once:
            report = service.run_cycle()
            return 2 if report.delivery_failures else 0
        if not args.dry_run:
            command_poller = TelegramCommandPoller(
                settings,
                database,
                [source.display_name for source in source_specs],
                event_store=runtime.event_store,
            )
            command_poller.start()
        LOGGER.info("Starting %s-minute scheduler", settings.poll_interval_minutes)
        run_scheduler(service, settings.poll_interval_minutes)
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Hackathon Radar stopped")
    finally:
        if command_poller:
            command_poller.stop()
        runtime.close()
        notifier.close()
    return 0


def build_runtime(
    settings: Settings,
    database: Database,
    notifier: ConsoleNotifier | TelegramClient,
    source_specs: list[SourceSpec],
    *,
    dry_run: bool,
) -> Runtime:
    if dry_run:
        return Runtime(
            RadarService(
                settings,
                database,
                notifier,
                source_specs,
                dry_run=True,
            )
        )
    event_store = EventStore(settings.database_path)
    event_store.init()
    planner = AlertPlanner(preferences_from_mapping(event_store.load_preferences()))
    verifier = URLVerifier(timeout_seconds=settings.http_timeout_seconds)
    service = RadarService(
        settings,
        database,
        notifier,
        source_specs,
        event_store=event_store,
        planner=planner,
        url_verifier=verifier,
    )
    return Runtime(service, event_store, verifier)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll hackathon sources and notify Telegram")
    parser.add_argument("--run-once", action="store_true", help="run one polling cycle and exit")
    parser.add_argument(
        "--dry-run", action="store_true", help="print alerts without sending or writing"
    )
    parser.add_argument(
        "--notify-existing",
        action="store_true",
        help="send currently listed hackathons instead of creating a safe first-run baseline",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


if __name__ == "__main__":
    raise SystemExit(main())
