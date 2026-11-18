from __future__ import annotations

import argparse
from pathlib import Path

from config import Settings
from offsite_backup import TelegramDocumentStore, run_offsite_backup


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Path(args.database) if args.database else settings.database_path
    store = TelegramDocumentStore(settings)
    try:
        result = run_offsite_backup(database, args.catalog, store)
    finally:
        store.close()
    print(
        f"verified message={result.stable_message_id} size={result.size} "
        f"sha256={result.sha256} deleted={len(result.deleted_messages)}"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload, restore-test, and retain the latest SQLite backup in Telegram"
    )
    parser.add_argument("--database", help="database path; defaults to DATABASE_PATH")
    parser.add_argument(
        "--catalog",
        default="offsite_backups.json",
        help="mode-600 local catalog for the stable Telegram message",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
