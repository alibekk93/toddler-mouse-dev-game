"""Particle bursts. Confetti and the sparkle trail arrive at M4.

Nothing here flashes above 3Hz (UX §7): a burst is a single fade-out, not a strobe.
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsObject

from ...timing import POP_MS


class Burst(QGraphicsObject):
    """A small outward spray that fades and then removes itself."""

    def __init__(self, colour: QColor, radius: float, count: int = 14) -> None:
        super().__init__()
        self._colour = QColor(colour)
        self._radius = radius
        self._elapsed = 0.0
        self.setZValue(500)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        rng = random.Random()
        self._particles = [
            (
                rng.uniform(0, 2 * math.pi),
                rng.uniform(0.45, 1.0) * radius * 1.5,
                rng.uniform(0.10, 0.22) * radius,
            )
            for _ in range(count)
        ]

    def boundingRect(self) -> QRectF:
        reach = self._radius * 2.0
        return QRectF(-reach, -reach, reach * 2, reach * 2)

    def tick(self, elapsed_ms: int) -> bool:
        """Advance; returns False once it is finished and should be removed."""
        self._elapsed += elapsed_ms
        self.update()
        return self._elapsed < POP_MS

    def paint(self, painter: QPainter, option, widget=None) -> None:
        t = min(1.0, self._elapsed / POP_MS)
        eased = 1 - (1 - t) ** 3
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        colour = QColor(self._colour)
        colour.setAlphaF(max(0.0, 1.0 - t))
        painter.setBrush(QBrush(colour))
        for angle, distance, size in self._particles:
            centre = QPointF(math.cos(angle) * distance * eased, math.sin(angle) * distance * eased)
            r = size * (1.0 - 0.5 * t)
            painter.drawEllipse(centre, r, r)
