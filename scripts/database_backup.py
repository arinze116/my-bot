from __future__ import annotations

import argparse
from pathlib import Path

from config import Settings
from database_backup import backup_database, restore_database


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    settings = Settings.from_env()
    database = Path(args.database) if args.database else settings.database_path
    if args.action == "backup":
        backup = backup_database(database, args.output_dir)
        print(backup)
        return 0
    result = restore_database(
        args.backup,
        database,
        replace=args.replace,
    )
    print(result.database_path)
    if result.recovery_path is not None:
        print(result.recovery_path)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or restore a verified SQLite snapshot")
    subparsers = parser.add_subparsers(dest="action", required=True)
    backup = subparsers.add_parser("backup", help="create a consistent SQLite snapshot")
    backup.add_argument("--database", help="database path; defaults to DATABASE_PATH")
    backup.add_argument("--output-dir", default="backups", help="snapshot directory")
    restore = subparsers.add_parser("restore", help="restore a verified SQLite snapshot")
    restore.add_argument("--backup", required=True, help="snapshot to restore")
    restore.add_argument("--database", help="database path; defaults to DATABASE_PATH")
    restore.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing database after saving a recovery snapshot",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
