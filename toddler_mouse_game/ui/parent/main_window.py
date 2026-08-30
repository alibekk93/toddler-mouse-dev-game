"""Parent window.

At M0 this is the Play page's two buttons and nothing else — the app starts here, a
grown-up deliberately starts an activity (SPEC §1). The nav shell and the other five
pages arrive at M3.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


class MainWindow(QWidget):
    """Emits `start_activity` when a grown-up presses Play or Warm-up."""

    start_activity = Signal()

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
        layout.addStretch(1)

        # Both open the same blank kid window at M0; M2 gives the signal an activity.
        for text in ("Play", "Warm-up"):
            button = QPushButton(text)
            button.setMinimumHeight(72)
            button.setStyleSheet("font-size: 18px;")
            button.clicked.connect(self.start_activity)
            layout.addWidget(button)

        layout.addStretch(1)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        QApplication.quit()  # quitOnLastWindowClosed is off; see app.py
