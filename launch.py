"""PyInstaller entry point (ROADMAP M6). Not used when running from source.

`python -m toddler_mouse_game` is the normal way in, but PyInstaller cannot pack a
`-m` invocation: it needs a plain script, and running `__main__.py` as one breaks its
relative imports (`from .app import run`). So the frozen build starts here instead, and
this file exists for no other reason.

    pyinstaller --noconfirm --windowed --onedir --name "Where Is It" \
      --add-data "toddler_mouse_game/assets;toddler_mouse_game/assets" launch.py
"""

import sys

from toddler_mouse_game.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
