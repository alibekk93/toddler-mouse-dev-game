"""Warm-up: drifting shapes she can pop. No questions, no right answer, no voice.

SPEC §3. This exists because the quiz asks her to learn two things at once — *move my
hand and the thing on screen moves with it*, and *this sound means that picture*. The
first is a motor skill, the second is language. Warm-up isolates the motor skill so it
can be practised where no wrong answer exists.

It imports nothing from `core/library.py` and must stay runnable on a completely empty
library, which also makes it the fastest way to test cursor feel in isolation.
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from ...timing import SHAPE_CROSS_SECONDS, SHAPE_RESPAWN_MS
from .card import HoverTile
from .effects import Burst

MARGIN = 0.05  # shapes never enter the outer 5% (SPEC §3)
IDEAL_SIZE = 0.40  # of screen height: the size of a quiz card at n=4 (UX §6)
# ponytail: six shapes at 40% of height cannot fit without overlapping, and overlap
# would make a click ambiguous. Shrink to a packing fraction when crowded; raise
# PACKING if they feel too small on the real screen.
PACKING = 0.45
SEPARATION = 1.06  # keep this much of the summed radii between neighbours

PALETTE = [
    ("#f2b134", "circle"),
    ("#e15554", "star"),
    ("#3bb273", "circle"),
    ("#4d9de0", "flower"),
    ("#e1bc29", "star"),
    ("#7768ae", "circle"),
    ("#ef8354", "flower"),
    ("#2fb5a8", "star"),
]


class Shape(HoverTile):
    """A soft vector shape. Behaviour is a card's; only the drawing differs."""

    def __init__(self, side: float, colour: str, kind: str) -> None:
        super().__init__(side)
        self.colour = QColor(colour)
        self.kind = kind
        self.velocity = QPointF(0, 0)
        self.popped = False

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.tile_rect()
        glow = 0.5 + 0.5 * math.sin(self._glow_phase) if self.is_hovering() else 0.0
        outline = QColor("#2b2118")
        highlight = QColor(255, 255, 255, int(90 * glow))

        painter.setPen(QPen(outline, self._side * 0.035))
        painter.setBrush(QBrush(self.colour))
        if self.kind == "circle":
            painter.drawEllipse(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 70)))
            painter.drawEllipse(
                rect.center() + QPointF(-self._side * 0.16, -self._side * 0.18),
                self._side * 0.11,
                self._side * 0.09,
            )
        elif self.kind == "star":
            painter.drawPolygon(self._star(rect))
        else:
            self._flower(painter, rect)

        if glow:
            painter.setPen(QPen(highlight, self._side * 0.06))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                rect.adjusted(
                    -self._side * 0.03, -self._side * 0.03, self._side * 0.03, self._side * 0.03
                )
            )

    def _star(self, rect: QRectF) -> QPolygonF:
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            r = self._side / 2 * (1.0 if i % 2 == 0 else 0.46)
            points.append(rect.center() + QPointF(r * math.cos(angle), r * math.sin(angle)))
        return QPolygonF(points)

    def _flower(self, painter: QPainter, rect: QRectF) -> None:
        petal = self._side * 0.26
        for i in range(6):
            angle = i * math.pi / 3
            centre = rect.center() + QPointF(
                math.cos(angle) * self._side * 0.22, math.sin(angle) * self._side * 0.22
            )
            painter.drawEllipse(centre, petal, petal)


class WarmupActivity:
    """Drifting shapes that pop. Runs until a grown-up exits, same as the quiz."""

    def __init__(self, scene, settings, sfx, rng: random.Random | None = None) -> None:
        self._scene = scene
        self._settings = settings
        self._sfx = sfx
        self._rng = rng or random.Random()
        self._shapes: list[Shape] = []
        self._bursts: list[Burst] = []
        self._respawn_queue: list[tuple[float, Shape]] = []

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        count = max(4, min(8, self._settings.warmup_shape_count))
        rect = self._scene.sceneRect()
        side = self._shape_side(count, rect)
        for index in range(count):
            colour, kind = PALETTE[index % len(PALETTE)]
            shape = Shape(side, colour, kind)
            self._place_clear(shape, rect)
            shape.appear(delay_ms=index * 90)
            self._scene.addItem(shape)
            self._shapes.append(shape)
        # Rejection sampling alone leaves overlaps once the screen gets busy (n=7, 8),
        # and an overlap makes a click ambiguous. Settle before the first frame.
        self._settle()

    def stop(self) -> None:
        for item in [*self._shapes, *self._bursts]:
            self._scene.removeItem(item)
        self._shapes.clear()
        self._bursts.clear()
        self._respawn_queue.clear()

    def tiles(self) -> list[HoverTile]:
        return [s for s in self._shapes if not s.popped]

    # -- placement ---------------------------------------------------------

    def _shape_side(self, count: int, rect: QRectF) -> float:
        play = (rect.width() * (1 - 2 * MARGIN)) * (rect.height() * (1 - 2 * MARGIN))
        return min(IDEAL_SIZE * rect.height(), math.sqrt(play * PACKING / count))

    def _bounds(self, rect: QRectF, side: float) -> tuple[float, float, float, float]:
        margin = MARGIN * min(rect.width(), rect.height())
        half = side / 2
        return (
            margin + half,
            margin + half,
            rect.width() - margin - half,
            rect.height() - margin - half,
        )

    def _place_clear(self, shape: Shape, rect: QRectF) -> None:
        left, top, right, bottom = self._bounds(rect, shape.side)
        best, best_gap = QPointF((left + right) / 2, (top + bottom) / 2), -1.0
        for _ in range(60):  # rejection sampling: cheap, and n is at most 8
            candidate = QPointF(self._rng.uniform(left, right), self._rng.uniform(top, bottom))
            gap = min(
                (
                    self._distance(candidate, o.pos()) - (shape.side + o.side) / 2
                    for o in self._shapes
                    if o is not shape and not o.popped
                ),
                default=1e9,
            )
            if gap > best_gap:
                best, best_gap = candidate, gap
            if gap > shape.side * 0.25:
                break
        shape.place(best.x() - shape.side / 2, best.y() - shape.side / 2, shape.side)
        self._clamp(shape, rect)
        seconds = self._rng.uniform(*SHAPE_CROSS_SECONDS)
        speed = rect.width() / seconds / 1000.0  # px per ms
        angle = self._rng.uniform(0, 2 * math.pi)
        shape.velocity = QPointF(math.cos(angle) * speed, math.sin(angle) * speed)

    @staticmethod
    def _distance(a: QPointF, b: QPointF) -> float:
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    # -- the frame clock ---------------------------------------------------

    def tick(self, elapsed_ms: int) -> None:
        rect = self._scene.sceneRect()
        live = [s for s in self._shapes if not s.popped]

        for shape in self._shapes:
            shape.tick(elapsed_ms)

        for shape in live:
            left, top, right, bottom = self._bounds(rect, shape.side)
            position = shape.pos() + shape.velocity * elapsed_ms
            vx, vy = shape.velocity.x(), shape.velocity.y()
            # Bounce softly off the margin rather than wrapping, so nothing ever
            # disappears off an edge she is watching.
            if position.x() < left or position.x() > right:
                vx = -vx
                position.setX(min(max(position.x(), left), right))
            if position.y() < top or position.y() > bottom:
                vy = -vy
                position.setY(min(max(position.y(), top), bottom))
            shape.velocity = QPointF(vx, vy)
            shape.setPos(position)

        self._separate(live)
        for shape in live:
            self._clamp(shape, rect)  # separation must not shove a shape off the edge
        self._advance_respawns(elapsed_ms, rect)

        for burst in list(self._bursts):
            if not burst.tick(elapsed_ms):
                self._scene.removeItem(burst)
                self._bursts.remove(burst)

    def _settle(self, iterations: int = 80) -> None:
        rect = self._scene.sceneRect()
        live = [s for s in self._shapes if not s.popped]
        for _ in range(iterations):
            self._separate(live)
            for shape in live:
                self._clamp(shape, rect)

    def _clamp(self, shape: Shape, rect: QRectF) -> None:
        left, top, right, bottom = self._bounds(rect, shape.side)
        shape.setPos(
            min(max(shape.pos().x(), left), right),
            min(max(shape.pos().y(), top), bottom),
        )

    def _separate(self, live: list[Shape]) -> None:
        """Shapes drift apart, so every click has one unambiguous owner (SPEC §3)."""
        for i, a in enumerate(live):
            for b in live[i + 1 :]:
                delta = b.pos() - a.pos()
                distance = math.hypot(delta.x(), delta.y()) or 0.001
                wanted = (a.side + b.side) / 2 * SEPARATION
                if distance >= wanted:
                    continue
                push = (wanted - distance) / 2
                unit = QPointF(delta.x() / distance, delta.y() / distance)
                a.setPos(a.pos() - unit * push)
                b.setPos(b.pos() + unit * push)

    def _advance_respawns(self, elapsed_ms: int, rect: QRectF) -> None:
        still_waiting = []
        for remaining, shape in self._respawn_queue:
            remaining -= elapsed_ms
            if remaining > 0:
                still_waiting.append((remaining, shape))
                continue
            shape.popped = False
            shape.setOpacity(0.0)
            shape._opacity_target = 1.0
            self._place_clear(shape, rect)
            self._settle()
            shape.appear()
            self._sfx.play("whoosh", 0.6)
        self._respawn_queue = still_waiting

    # -- input -------------------------------------------------------------

    def on_hover(self, tile: HoverTile | None) -> None:
        if tile is not None:
            self._sfx.play("tick")

    def on_click(self, tile: HoverTile | None) -> None:
        """Pop it. Clicking the background does nothing at all, silently (UX §6)."""
        if tile is None or not isinstance(tile, Shape) or tile.popped:
            return
        tile.popped = True
        tile.set_hovering(False)
        tile._opacity_target = 0.0
        tile._scale_base = 0.6

        burst = Burst(tile.colour, tile.side / 2)
        burst.setPos(tile.pos())
        self._scene.addItem(burst)
        self._bursts.append(burst)
        self._sfx.play("pop")
        self._respawn_queue.append((SHAPE_RESPAWN_MS, tile))
