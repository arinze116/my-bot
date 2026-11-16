from __future__ import annotations

from pathlib import Path

from commands import TelegramCommandPoller
from config import Settings
from db import Database
from sources import enabled_sources

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AVATAR_PATH = PROJECT_ROOT / "brand" / "hackathon-radar-avatar.jpg"


def main() -> int:
    settings = Settings.from_env()
    settings.validate_telegram()
    database = Database(settings.database_path)
    database.init()
    source_names = [source.display_name for source in enabled_sources(settings)]
    poller = TelegramCommandPoller(settings, database, source_names)
    try:
        identity_ok = poller.customize_bot()
        avatar_ok = poller.set_profile_photo(AVATAR_PATH)
    finally:
        poller.stop()
    print(f"Bot identity: {'updated' if identity_ok else 'failed'}")
    print(f"Profile photo: {'updated' if avatar_ok else 'failed'}")
    return 0 if identity_ok and avatar_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
