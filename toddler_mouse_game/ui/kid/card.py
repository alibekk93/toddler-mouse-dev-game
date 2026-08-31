"""Tiles she can point at: quiz cards, and the warm-up shapes that share their feel.

`HoverTile` exists because SPEC §3 requires the warm-up shapes to react to the cursor
*exactly* as a quiz card does — the whole point of warm-up is that the motor skill
transfers, so nothing about the interaction may differ. One base, two paints.

Every visual state change is paired with a scale or motion change, never colour alone
(UX §7), and every transition is eased on the frame clock rather than owned by a
QPropertyAnimation, so the three that overlap (appear, hover, celebrate) cannot fight.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsObject

from ...timing import (
    CARD_APPEAR_MS,
    HOVER_SCALE,
    PRESS_SCALE,
    WOBBLE_DEGREES,
    WOBBLE_MS,
)

EASE = 0.22
PANEL = QColor("#f4efe4")  # light neutral matting, so a dark photo and a white PNG
BORDER = QColor("#e8dcc4")  # both read as the same kind of object (UX §7)
BORDER_HOVER = QColor("#fff6e2")
SHADOW = QColor(0, 0, 0, 70)
GLOW_MS = 1800
CORNER = 0.07  # of the tile side


def _ease_out_back(t: float) -> float:
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


class HoverTile(QGraphicsObject):
    """A rounded tile with the UX §2 feedback ladder built in.

    The item's origin is its centre, which is what makes scaling and the wrong-answer
    head-shake rotate about the middle instead of a corner.
    """

    def __init__(self, side: float) -> None:
        super().__init__()
        self._side = side
        self._hover = 1.0
        self._hover_target = 1.0
        self._press = 1.0
        self._press_target = 1.0
        self._scale_base = 1.0
        self._opacity_target = 1.0
        self._pos_target: QPointF | None = None
        self._appear_ms = 0.0
        self._appear_delay_ms = 0.0
        self._wobble_ms = -1.0
        self._glow_phase = 0.0
        self._hovering = False
        self.setOpacity(0.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # the view does hit-testing

    # -- geometry ----------------------------------------------------------

    @property
    def side(self) -> float:
        return self._side

    def boundingRect(self) -> QRectF:
        half = self._side / 2
        margin = self._side * 0.06  # room for the shadow
        return QRectF(
            -half - margin, -half - margin, self._side + 2 * margin, self._side + 2 * margin
        )

    def tile_rect(self) -> QRectF:
        half = self._side / 2
        return QRectF(-half, -half, self._side, self._side)

    def shape(self) -> QPainterPath:
        """Hit area is exactly the drawn tile, not the shadow margin around it.

        Invisible hit padding was considered and declined (FUTURE_IDEAS); revisit only
        if near-misses turn out to be common in real play.
        """
        path = QPainterPath()
        radius = self._side * CORNER
        path.addRoundedRect(self.tile_rect(), radius, radius)
        return path

    def place(self, x: float, y: float, side: float) -> None:
        self.prepareGeometryChange()
        self._side = side
        self.setPos(x + side / 2, y + side / 2)

    # -- state -------------------------------------------------------------

    def appear(self, delay_ms: float = 0.0) -> None:
        self._appear_ms = 0.0
        self._appear_delay_ms = delay_ms
        self.setOpacity(0.0)

    def set_hovering(self, hovering: bool) -> None:
        if hovering == self._hovering:
            return
        self._hovering = hovering
        self._hover_target = HOVER_SCALE if hovering else 1.0
        if not hovering:
            self._glow_phase = 0.0

    def is_hovering(self) -> bool:
        return self._hovering

    def set_pressed(self, pressed: bool) -> None:
        self._press_target = PRESS_SCALE if pressed else 1.0

    def wobble(self) -> None:
        """The wrong-answer head-shake: 'mm, not that one', never a failure (SPEC §2.4)."""
        self._wobble_ms = 0.0

    def celebrate_to(self, centre: QPointF, scale: float) -> None:
        self._pos_target = centre
        self._scale_base = scale

    def recede(self) -> None:
        """What the other cards do while the chosen one is celebrating."""
        self._scale_base = 0.85
        self._opacity_target = 0.0

    def fade_out(self) -> None:
        self._opacity_target = 0.0

    # -- the frame clock ---------------------------------------------------

    def tick(self, elapsed_ms: int) -> None:
        if self._appear_delay_ms > 0:
            self._appear_delay_ms -= elapsed_ms
            return

        appear = 1.0
        if self._appear_ms < CARD_APPEAR_MS:
            self._appear_ms = min(CARD_APPEAR_MS, self._appear_ms + elapsed_ms)
            appear = self._appear_ms / CARD_APPEAR_MS

        self._hover += (self._hover_target - self._hover) * EASE
        self._press += (self._press_target - self._press) * EASE
        self.setOpacity(self.opacity() + (self._opacity_target * appear - self.opacity()) * EASE)

        if self._pos_target is not None:
            self.setPos(self.pos() + (self._pos_target - self.pos()) * EASE)

        pop = _ease_out_back(appear) if appear < 1.0 else 1.0
        self.setScale(self._scale_base * self._hover * self._press * (0.72 + 0.28 * pop))

        if self._wobble_ms >= 0:
            self._wobble_ms += elapsed_ms
            t = self._wobble_ms / WOBBLE_MS
            if t >= 1.0:
                self._wobble_ms = -1.0
                self.setRotation(0.0)
            else:
                # two shakes, decaying — soft, and over in 400ms
                self.setRotation(WOBBLE_DEGREES * math.sin(t * 4 * math.pi) * (1 - t))

        if self._hovering:
            self._glow_phase += 2 * math.pi * elapsed_ms / GLOW_MS
            self.update()

    # -- painting ----------------------------------------------------------

    def _paint_frame(self, painter: QPainter) -> QRectF:
        rect = self.tile_rect()
        radius = self._side * CORNER

        shadow = rect.translated(0, self._side * 0.035)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(SHADOW))
        painter.drawRoundedRect(shadow, radius, radius)

        glow = 0.5 + 0.5 * math.sin(self._glow_phase) if self._hovering else 0.0
        colour = (
            BORDER
            if not self._hovering
            else QColor(
                int(BORDER.red() + (BORDER_HOVER.red() - BORDER.red()) * glow),
                int(BORDER.green() + (BORDER_HOVER.green() - BORDER.green()) * glow),
                int(BORDER.blue() + (BORDER_HOVER.blue() - BORDER.blue()) * glow),
            )
        )
        painter.setBrush(QBrush(PANEL))
        painter.setPen(QPen(colour, self._side * 0.045))
        painter.drawRoundedRect(rect, radius, radius)
        return rect


class Card(HoverTile):
    """A picture on a tile. Letterboxed, never cropped: a cat with its head cropped
    off is not a cat to her (UX §1)."""

    def __init__(self, side: float, pixmap: QPixmap, image_id: str = "") -> None:
        super().__init__(side)
        self._pixmap = pixmap
        self.image_id = image_id

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self._paint_frame(painter)
        if self._pixmap.isNull():
            return
        inner = rect.adjusted(
            self._side * 0.08, self._side * 0.08, -self._side * 0.08, -self._side * 0.08
        )
        scaled = self._pixmap.size().scaled(
            inner.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio
        )
        target = QRectF(0, 0, scaled.width(), scaled.height())
        target.moveCenter(inner.center())
        painter.drawPixmap(target.toRect(), self._pixmap)
