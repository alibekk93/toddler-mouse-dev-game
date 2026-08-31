"""Parent window.

At M0 this is the Play page's two buttons and nothing else — the app starts here, a
grown-up deliberately starts an activity (SPEC §1). The nav shell and the other five
pages arrive at M3.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


class MainWindow(QWidget):
    """Emits `start_activity` when a grown-up presses Play or Warm-up."""

    start_activity = Signal(str)  # "quiz" or "warmup"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Where Is It?")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(20)

        heading = QLabel("Where Is It?")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(heading)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)
        layout.addStretch(1)

        # The other five pages arrive at M3.
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
        """Only Play is ever disabled. Warm-up needs no content, so it always works —
        including on the very first run, before a single picture has been added."""
        self._buttons["quiz"].setEnabled(ready)
        self._buttons["quiz"].setToolTip("" if ready else reason)
        self._status.setText(reason)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        QApplication.quit()  # quitOnLastWindowClosed is off; see app.py
