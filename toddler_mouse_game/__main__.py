"""Entry point: `python -m toddler_mouse_game --library ../library`."""

import argparse
import os
import sys
from pathlib import Path

from .app import run


def _default_library() -> Path:
    """DATA_MODEL §2 step 3. Step 2 (`last_library` in the app config) arrives at M5."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "BuskaGame" / "library"
    return Path.home() / ".local" / "share" / "BuskaGame" / "library"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="toddler_mouse_game", description="Where Is It?")
    parser.add_argument(
        "--library",
        type=Path,
        default=_default_library(),
        help="library folder (default: %(default)s)",
    )
    parser.add_argument(
        "--kid",
        action="store_true",
        help="start straight in kid mode instead of the parent window",
    )
    args = parser.parse_args(argv)
    return run(args.library, args.kid)


if __name__ == "__main__":
    sys.exit(main())
