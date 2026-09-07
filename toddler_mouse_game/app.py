"""QApplication, the parent <-> kid mode switch, and lifecycle."""

import random
import sys
from contextlib import ExitStack
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .audio import player as player_mod
from .core import library as library_mod
from .core import settings as settings_mod
from .core.round_builder import RoundBuilder, readiness
from .platform import windows as hardening
from .ui.kid.scene import KidScene
from .ui.kid.session import QuizSession
from .ui.kid.warmup import WarmupActivity
from .ui.kid.window import KidWindow
from .ui.parent.main_window import MainWindow


def run(library_dir: Path, start_in_kid_mode: bool = False) -> int:
    """Start the app. Returns the Qt exit code."""
    # Must be set before the QApplication exists (ARCHITECTURE §4.3).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Where Is It?")
    # Kid mode hides the parent window, so "no windows visible" is a normal state and
    # must not quit the app. MainWindow.closeEvent quits explicitly.
    app.setQuitOnLastWindowClosed(False)

    library_dir = Path(library_dir)
    settings = settings_mod.load(library_dir)
    library, issues = library_mod.load(library_dir)
    for issue in issues:
        print(f"library: {issue.message}")
    if not player_mod.AVAILABLE:
        print(f"audio unavailable, running silent: {player_mod.UNAVAILABLE_REASON}")

    player = player_mod.Player(settings.master_volume)
    sfx = player_mod.Sfx(player)

    # Both windows are held in this frame, which app.exec() blocks inside — a Qt window
    # that only the C++ side references gets garbage collected out from under it.
    parent = MainWindow(library, settings)
    kid = KidWindow()
    session = ExitStack()  # holds the SPEC §7 defences for the length of the session

    def enter_kid(activity_name: str) -> None:
        scene = KidScene(settings.cursor_style, settings.cursor_scale)
        if activity_name == "warmup":
            activity = WarmupActivity(scene, settings, sfx)
        else:
            library_mod.validate(library, settings.option_count)
            builder = RoundBuilder(library, settings, seed=random.randrange(1 << 30))
            activity = QuizSession(scene, library, settings, builder, player, sfx)
            activity.finished.connect(leave_kid)

        parent.hide()
        kid.start(activity, scene, sprite_cursor=settings.cursor_mode != "hardware")

        session.enter_context(hardening.hardened_session(kid.clip_rect()))
        for failure in hardening.failures():
            print(f"session hardening: {failure}")  # log it and carry on

    def leave_kid() -> None:
        session.close()  # releases the display lock and unclips the cursor
        player.stop_all()
        if kid.isVisible():
            kid.hide()
        # Play is disabled with a plain reason when no round can be built (SPEC §4.1).
        # The parent pages re-check this themselves whenever they change content.
        parent.refresh()
        parent.show()
        parent.raise_()
        parent.activateWindow()

    parent.start_activity.connect(enter_kid)
    kid.exited.connect(leave_kid)
    app.aboutToQuit.connect(hardening.release_all)  # belt, alongside the atexit hook

    ok, _reason = readiness(library, settings)
    if start_in_kid_mode:
        enter_kid("quiz" if ok else "warmup")
    else:
        parent.show()

    return app.exec()
