from __future__ import annotations

import time

from config import Settings
from sources import enabled_sources


def main() -> int:
    settings = Settings.from_env()
    failures = 0
    for source in enabled_sources(settings):
        started = time.monotonic()
        try:
            items = source.fetch()
            elapsed = time.monotonic() - started
            print(f"PASS {source.name}: {len(items)} items in {elapsed:.2f}s")
        except Exception as error:
            failures += 1
            elapsed = time.monotonic() - started
            print(f"FAIL {source.name}: {type(error).__name__}: {error} ({elapsed:.2f}s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
