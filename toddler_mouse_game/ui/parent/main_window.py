"""Parent window: a nav strip on the left, one page at a time on the right.

Three pages at M3 — Play, Images, Sounds. Settings, Progress, and Backup (SPEC §4.4-4.6)
join the nav at M5, when the pages behind them exist; a nav entry that opens an empty
placeholder is worse than no nav entry.

This window owns the loaded `Library` and hands its pages one `save` callback, so there
is exactly one place that writes the manifest and exactly one place that re-checks
readiness afterwards.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QWidget,
)

from ...core import library as library_mod
from ...core import settings as settings_mod
from ...core.library import Library
from ...core.models import Settings
from ...core.round_builder import readiness
from .images_page import ImagesPage
from .play_page import PlayPage
from .sounds_page import SoundsPage


class MainWindow(QWidget):
    """Emits `start_activity` when a grown-up presses Play or Warm-up."""

    start_activity = Signal(str)  # "quiz" or "warmup"

    def __init__(self, library: Library, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("Where Is It?")
        self.resize(900, 620)

        self._library = library
        self._settings = settings

        self._play = PlayPage(settings)
        self._play.start_activity.connect(self.start_activity)

        self._nav = QListWidget()
        self._nav.setFixedWidth(150)
        self._nav.setStyleSheet(
            "QListWidget { font-size: 15px; } QListWidget::item { padding: 10px; }"
        )
        self._stack = QStackedWidget()
        for name, page in (
            ("Play", self._play),
            ("Pictures", ImagesPage(library, settings, self.save, self.save_settings)),
            ("Sounds", SoundsPage(library, self.save)),
        ):
            self._nav.addItem(name)
            self._stack.addWidget(page)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)

        self.refresh()

    def save(self) -> None:
        """Persist the manifest and re-check whether the quiz can run.

        Every page calls this after changing content, so adding a picture on the Pictures
        page updates the Play button without a restart.
        """
        library_mod.save(self._library)
        self.refresh()

    def save_settings(self) -> None:
        """Persist settings.json. Separate from `save` because the manifest describes
        content and settings describe play — a page changing one must not rewrite the
        other (DATA_MODEL §5)."""
        settings_mod.save(self._library.root, self._settings)
        self.refresh()

    def refresh(self) -> None:
        self._play.set_readiness(*readiness(self._library, self._settings))

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        QApplication.quit()  # quitOnLastWindowClosed is off; see app.py
