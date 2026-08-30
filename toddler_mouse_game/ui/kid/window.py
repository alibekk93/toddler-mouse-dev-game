"""The fullscreen kid window.

At M0 it is a blank background and the way out. The scene, cards, and cursor sprite
go inside it at M2.

Kid mode is frameless, always on top, and swallows every key, so the exit is the
load-bearing part: hold `Esc` for 3 seconds and a ring fills so the grown-up can see
it working. A tap does nothing at all — a 2-year-old mashes keys (SPEC §1).
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...timing import ESC_HOLD_MS, RING_TICK_MS

BACKGROUND = QColor("#1b4442")  # warm deep teal; never white at fullscreen brightness
RING = QColor("#f2e9d8")
RING_TRACK = QColor(242, 233, 216, 60)

RING_DIAMETER = 0.18  # of the shorter screen edge — fractions, never fixed pixels
RING_THICKNESS = 0.09  # of the ring diameter


class KidWindow(QWidget):
    """Fullscreen, frameless, no chrome, no text. Emits `exited` on the way out."""

    exited = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._hold_ms = 0
        self._hold_timer = QTimer(self)
        self._hold_timer.setInterval(RING_TICK_MS)
        self._hold_timer.timeout.connect(self._on_hold_tick)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Go fullscreen on the primary screen and take keyboard focus."""
        self._reset_hold()
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())  # single monitor is a fixed constraint
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _exit(self) -> None:
        self._reset_hold()
        self.hide()
        self.exited.emit()

    def closeEvent(self, event) -> None:  # Alt+F4 — cannot be blocked, so handle it
        self._reset_hold()
        super().closeEvent(event)
        self.exited.emit()

    # -- the Esc hold ------------------------------------------------------

    def _reset_hold(self) -> None:
        self._hold_timer.stop()
        self._hold_ms = 0

    def _on_hold_tick(self) -> None:
        self._hold_ms += RING_TICK_MS
        if self._hold_ms >= ESC_HOLD_MS:
            self._exit()
        else:
            self.update()

    def keyPressEvent(self, event) -> None:
        # isAutoRepeat matters on both handlers: a held key repeats presses on Windows
        # and press/release pairs on X11. Without the guard the hold restarts every
        # repeat and the ring never fills.
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            if not self._hold_timer.isActive():
                self._hold_ms = 0
                self._hold_timer.start()
                self.update()
            return

        mods = event.modifiers()
        if (
            event.key() == Qt.Key.Key_P
            and mods & Qt.KeyboardModifier.ControlModifier
            and mods & Qt.KeyboardModifier.ShiftModifier
        ):
            self._exit()
            return

        # Every other key is swallowed. Do not call super().

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            self._reset_hold()
            self.update()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), BACKGROUND)

        if not self._hold_timer.isActive():
            return

        side = min(self.width(), self.height())
        diameter = side * RING_DIAMETER
        rect = QRectF(0, 0, diameter, diameter)
        rect.moveCenter(QPointF(self.width() / 2, self.height() / 2))

        pen = QPen(
            RING_TRACK,
            diameter * RING_THICKNESS,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.drawEllipse(rect)  # track, drawn from the first frame so it reacts at once

        progress = min(self._hold_ms / ESC_HOLD_MS, 1.0)
        pen.setColor(RING)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * progress))  # clockwise from 12
