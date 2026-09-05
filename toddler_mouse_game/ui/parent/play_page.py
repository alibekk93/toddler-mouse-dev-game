"""The Play page (SPEC §4.1): two big buttons and an honest readiness line.

Warm-up needs no content and is therefore never disabled, including on the very first
run before a single picture has been added. Only **Play** is ever blocked, and when it
is, the reason is stated plainly rather than left as a button that does nothing.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.models import Settings


class PlayPage(QWidget):
    """Emits `start_activity` when a grown-up presses Play or Warm-up."""

    start_activity = Signal(str)  # "quiz" or "warmup"

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)

        heading = QLabel("Where Is It?")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(heading)

        self._summary = QLabel("")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary.setStyleSheet("color: #888;")
        layout.addWidget(self._summary)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._buttons = {}
        for text, activity in (("Play", "quiz"), ("Warm-up", "warmup")):
            button = QPushButton(text)
            button.setMinimumHeight(72)
            button.setStyleSheet("font-size: 18px;")
            button.clicked.connect(lambda _=False, a=activity: self.start_activity.emit(a))
            layout.addWidget(button)
            self._buttons[activity] = button

        layout.addStretch(1)

    def set_readiness(self, ready: bool, reason: str) -> None:
        """Only Play is ever disabled. Warm-up needs no content, so it always works."""
        self._buttons["quiz"].setEnabled(ready)
        self._buttons["quiz"].setToolTip("" if ready else reason)
        self._status.setText(reason)

        enabled = self._settings.enabled_categories
        categories = "all categories" if enabled is None else ", ".join(enabled) or "no categories"
        self._summary.setText(f"{self._settings.option_count} pictures at a time · {categories}")
