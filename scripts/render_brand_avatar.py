from __future__ import annotations

from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = PROJECT_ROOT / "brand" / "hackathon-radar-avatar.svg"
JPG_PATH = PROJECT_ROOT / "brand" / "hackathon-radar-avatar.jpg"


def main() -> int:
    png_data = cairosvg.svg2png(
        url=str(SVG_PATH),
        output_width=1024,
        output_height=1024,
    )
    with Image.open(BytesIO(png_data)) as image:
        image.convert("RGB").save(JPG_PATH, format="JPEG", quality=95, optimize=True)
    print(f"Rendered {JPG_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
