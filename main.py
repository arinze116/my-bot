from __future__ import annotations

import argparse
import logging
from dataclasses import replace

from aggregator import RadarService
from bot import ConsoleNotifier, TelegramClient
from config import Settings
from db import Database
from scheduler import run_scheduler
from sources import enabled_sources

LOGGER = logging.getLogger(__name__)


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
    service = RadarService(settings, database, notifier, source_specs, dry_run=args.dry_run)

    try:
        notifier.send_startup_message(
            database.total_seen(), [source.display_name for source in source_specs]
        )
        if args.run_once:
            report = service.run_cycle()
            return 2 if report.delivery_failures else 0
        LOGGER.info("Starting %s-minute scheduler", settings.poll_interval_minutes)
        run_scheduler(service, settings.poll_interval_minutes)
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Hackathon Radar stopped")
    finally:
        notifier.close()
    return 0


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
