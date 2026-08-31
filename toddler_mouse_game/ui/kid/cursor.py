"""The giant sprite cursor. This is the lesson, not a UI detail (UX §2).

ARCHITECTURE §4.1 picks the drawn sprite over a hardware cursor because the animation
is worth it, with one condition: it must not feel laggy. So the item's position is set
directly from `mouseMoveEvent` and never from a timer tick — a timer both misses fast
movement and adds a frame of delay, which reads as sluggish and undermines the exact
hand-to-screen link being taught.

Scale is eased toward a target on the frame clock rather than animated with
QPropertyAnimation objects, because three effects (hover grow, press squash, idle
breathing) multiply together and starting/stopping animations on each would fight.
"""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsObject

from ...timing import (
    CURSOR_BREATH_MS,
    CURSOR_BREATH_SCALE,
    CURSOR_HOVER_GROW,
    CURSOR_PRESS_SQUASH,
)

BASE_SIZE = 112.0  # logical px; UX §2 asks for 96-128, about a third of a card
EASE = 0.28  # how fast scale chases its target each frame
CURSOR_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "cursors"


class SpriteCursor(QGraphicsObject):
    """A friendly character that grows on a card and squashes when pressed."""

    def __init__(self, style: str = "paw", scale: float = 1.0) -> None:
        super().__init__()
        path = CURSOR_DIR / f"{style}.svg"
        if not path.is_file():
            path = CURSOR_DIR / "paw.svg"
        self._renderer = QSvgRenderer(str(path))

        self._user_scale = max(0.6, min(2.0, scale))
        self._grow = 1.0
        self._grow_target = 1.0
        self._press = 1.0
        self._press_target = 1.0
        self._phase = 0.0

        self.setZValue(1000)  # always on top of everything
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self._apply_scale()

    # -- geometry ----------------------------------------------------------

    def boundingRect(self) -> QRectF:
        half = BASE_SIZE / 2
        return QRectF(-half, -half, BASE_SIZE, BASE_SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._renderer.render(painter, self.boundingRect())

    def move_to(self, point: QPointF) -> None:
        """The hotspot is the visual centre, not a tip: she aims the middle of the blob."""
        self.setPos(point)

    # -- state -------------------------------------------------------------

    def set_hovering(self, hovering: bool) -> None:
        self._grow_target = CURSOR_HOVER_GROW if hovering else 1.0

    def set_pressed(self, pressed: bool) -> None:
        self._press_target = CURSOR_PRESS_SQUASH if pressed else 1.0

    def tick(self, elapsed_ms: int) -> None:
        """Advance the idle breath and ease the scale. Called on the frame clock."""
        self._phase += 2 * math.pi * elapsed_ms / CURSOR_BREATH_MS
        self._grow += (self._grow_target - self._grow) * EASE
        self._press += (self._press_target - self._press) * EASE
        self._apply_scale()

    def _apply_scale(self) -> None:
        # Parked at a screen edge it still breathes, so it never looks frozen (UX §2).
        breath = 1.0 + CURSOR_BREATH_SCALE * math.sin(self._phase)
        self.setScale(self._user_scale * self._grow * self._press * breath)

    def pixmap_size(self) -> int:
        return int(BASE_SIZE * self._user_scale)

    def renderer(self) -> QSvgRenderer:
        return self._renderer
