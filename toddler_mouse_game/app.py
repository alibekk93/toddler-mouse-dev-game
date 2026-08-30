"""QApplication, the parent <-> kid mode switch, and lifecycle."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .ui.kid.window import KidWindow
from .ui.parent.main_window import MainWindow


def run(library_dir: Path, start_in_kid_mode: bool = False) -> int:
    """Start the app. Returns the Qt exit code.

    `library_dir` is unused at M0 — nothing reads content yet. M1 loads the library
    and settings from it.
    """
    # Must be set before the QApplication exists (ARCHITECTURE §4.3).
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Where Is It?")
    # Kid mode hides the parent window, so "no windows visible" is a normal state and
    # must not quit the app. MainWindow.closeEvent quits explicitly.
    app.setQuitOnLastWindowClosed(False)

    # Both windows are held in this frame, which app.exec() blocks inside — a Qt window
    # that only the C++ side references gets garbage collected out from under it.
    parent = MainWindow()
    kid = KidWindow()

    def enter_kid() -> None:
        parent.hide()
        kid.start()

    def leave_kid() -> None:
        parent.show()
        parent.raise_()
        parent.activateWindow()

    parent.start_activity.connect(enter_kid)
    kid.exited.connect(leave_kid)

    if start_in_kid_mode:
        enter_kid()
    else:
        parent.show()

    return app.exec()
