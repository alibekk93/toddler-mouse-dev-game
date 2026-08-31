"""The kid-mode scene: background, tiles, and the sprite cursor.

This module renders and hit-tests. It holds no game state — that lives in
`session.py` (quiz) and `warmup.py`, per ARCHITECTURE §3.
"""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsScene

from .card import HoverTile
from .cursor import SpriteCursor

# Warm, low-saturation, and deliberately not white: white at fullscreen brightness is
# harsh at close range, and she sits 40cm away (UX §1).
BACKGROUND = QColor("#1b4442")


class KidScene(QGraphicsScene):
    def __init__(self, cursor_style: str = "paw", cursor_scale: float = 1.0) -> None:
        super().__init__()
        self.setBackgroundBrush(BACKGROUND)
        self.cursor_item = SpriteCursor(cursor_style, cursor_scale)
        self.addItem(self.cursor_item)
        self.cursor_item.hide()

    def set_size(self, width: float, height: float) -> None:
        """Everything is laid out in fractions of this rect, never in fixed pixels."""
        self.setSceneRect(QRectF(0, 0, width, height))

    def centre(self) -> QPointF:
        return self.sceneRect().center()

    def tile_at(self, point: QPointF) -> HoverTile | None:
        """Topmost tile under a scene point, ignoring the cursor and any effects."""
        for item in self.items(point):
            if isinstance(item, HoverTile) and item.isVisible() and item.opacity() > 0.15:
                return item
        return None
