"""The fullscreen kid window: a QGraphicsView that owns input and the way out.

All mouse handling lives here rather than on the items, for two reasons. The sprite
cursor must be repositioned in `mouseMoveEvent` itself — a timer both misses fast
movement and adds a frame of lag (ARCHITECTURE §4.1). And clicks have to be *forgiving*
in a way Qt's default item handling is not: UX §2 says a press that starts anywhere and
releases over a card counts as picking that card, because she will do that constantly.

Kid mode is frameless, always on top, and swallows every key, so the `Esc`-hold exit is
load-bearing: hold for three seconds and a ring fills so a grown-up can see it working.
A tap does nothing at all.
"""

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsView

from ...timing import CLICK_DEBOUNCE_MS, ESC_HOLD_MS, FRAME_MS, RING_TICK_MS
from .scene import BACKGROUND, KidScene

RING = QColor("#f2e9d8")
RING_TRACK = QColor(242, 233, 216, 60)
RING_SCRIM = QColor(12, 30, 29)  # dims the cards so the ring stays legible over them
RING_DIAMETER = 0.18  # of the shorter screen edge
RING_THICKNESS = 0.09  # of the ring diameter


class KidWindow(QGraphicsView):
    """Hosts one activity at a time. Emits `exited` on the way back to parent mode."""

    exited = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setBackgroundBrush(BACKGROUND)

        self._scene: KidScene | None = None
        self._activity = None
        self._sprite_cursor = True
        self._hovered = None
        self._pressed_tile = None
        self._last_click = QElapsedTimer()

        self._hold_ms = 0
        self._hold_timer = QTimer(self)
        self._hold_timer.setInterval(RING_TICK_MS)
        self._hold_timer.timeout.connect(self._on_hold_tick)

        self._frame = QTimer(self)
        self._frame.setInterval(FRAME_MS)
        self._frame.timeout.connect(self._on_frame)
        self._clock = QElapsedTimer()

    # -- lifecycle ---------------------------------------------------------

    def start(self, activity, scene: KidScene, sprite_cursor: bool = True) -> None:
        """Go fullscreen on the primary screen with `activity` running inside."""
        self._scene = scene
        self._activity = activity
        self._sprite_cursor = sprite_cursor
        self.setScene(scene)
        self._reset_hold()

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())  # single monitor is a fixed constraint
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()

        self._sync_scene_size()
        if sprite_cursor:
            self.viewport().setCursor(Qt.CursorShape.BlankCursor)
            scene.cursor_item.show()
        else:
            scene.cursor_item.hide()
            self.viewport().setCursor(self._hardware_cursor(scene))

        scene.cursor_item.move_to(self._scene_point(self.mapFromGlobal(QCursor.pos())))
        activity.start()
        self._clock.start()
        self._last_click.start()
        self._frame.start()

    def _hardware_cursor(self, scene: KidScene) -> QCursor:
        """The `cursor_mode: hardware` escape hatch, if the sprite feels laggy."""
        size = min(128, scene.cursor_item.pixmap_size())
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.cursor_item.renderer().render(painter, QRectF(0, 0, size, size))
        painter.end()
        return QCursor(pixmap, size // 2, size // 2)  # hotspot is the visual centre

    def _exit(self) -> None:
        self._frame.stop()
        self._reset_hold()
        if self._activity is not None:
            self._activity.stop()
        self._activity = None
        self.viewport().unsetCursor()
        self.hide()
        self.exited.emit()

    def closeEvent(self, event) -> None:  # Alt+F4 cannot be blocked, so handle it
        self._frame.stop()
        self._reset_hold()
        if self._activity is not None:
            self._activity.stop()
            self._activity = None
        super().closeEvent(event)
        self.exited.emit()

    # -- geometry ----------------------------------------------------------

    def _sync_scene_size(self) -> None:
        if self._scene is not None:
            size = self.viewport().size()
            self._scene.set_size(size.width(), size.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_scene_size()

    def _scene_point(self, view_point) -> QPointF:
        return self.mapToScene(view_point)

    # -- the frame clock ---------------------------------------------------

    def _on_frame(self) -> None:
        elapsed = self._clock.restart()
        if self._scene is not None:
            self._scene.cursor_item.tick(elapsed)
        if self._activity is not None:
            self._activity.tick(elapsed)

    # -- mouse -------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        if self._scene is None:
            return
        point = self._scene_point(event.position().toPoint())
        self._scene.cursor_item.move_to(point)  # directly, never on a timer tick
        self._update_hover(point)

    def _update_hover(self, point: QPointF) -> None:
        tile = self._scene.tile_at(point) if self._scene else None
        if tile is self._hovered:
            return
        if self._hovered is not None:
            self._hovered.set_hovering(False)
        self._hovered = tile
        if tile is not None:
            tile.set_hovering(True)
        self._scene.cursor_item.set_hovering(tile is not None)
        if tile is not None and self._activity is not None:
            self._activity.on_hover(tile)

    def mousePressEvent(self, event) -> None:
        # Right and middle click are treated exactly like left: she does not know the
        # difference and should not be punished for it (UX §2).
        if self._scene is None:
            return
        self._scene.cursor_item.set_pressed(True)
        self._pressed_tile = self._hovered
        if self._pressed_tile is not None:
            self._pressed_tile.set_pressed(True)

    def mouseReleaseEvent(self, event) -> None:
        if self._scene is None:
            return
        self._scene.cursor_item.set_pressed(False)
        if self._pressed_tile is not None:
            self._pressed_tile.set_pressed(False)
            self._pressed_tile = None

        # Forgiving, not correct: whatever the release lands on is what she picked,
        # regardless of where the press started. Drags are simply ignored.
        point = self._scene_point(event.position().toPoint())
        self._update_hover(point)
        tile = self._scene.tile_at(point)
        if tile is None or self._activity is None:
            return
        if self._last_click.isValid() and self._last_click.elapsed() < CLICK_DEBOUNCE_MS:
            return  # the second click of a rapid burst is discarded, not processed
        self._last_click.restart()
        self._activity.on_click(tile)

    # -- keyboard ----------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # isAutoRepeat matters on both handlers: a held key repeats presses on Windows
        # and press/release pairs on X11. Without the guard the hold restarts every
        # repeat and the ring never fills.
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            if not self._hold_timer.isActive():
                self._hold_ms = 0
                self._hold_timer.start()
                self.viewport().update()
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
            self.viewport().update()

    def _reset_hold(self) -> None:
        self._hold_timer.stop()
        self._hold_ms = 0

    def _on_hold_tick(self) -> None:
        self._hold_ms += RING_TICK_MS
        if self._hold_ms >= ESC_HOLD_MS:
            self._exit()
        else:
            self.viewport().update()

    # -- the Esc ring ------------------------------------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self._hold_timer.isActive():
            return
        scene_rect = self.sceneRect()
        side = min(scene_rect.width(), scene_rect.height())
        diameter = side * RING_DIAMETER
        ring = QRectF(0, 0, diameter, diameter)
        ring.moveCenter(scene_rect.center())

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        progress = min(self._hold_ms / ESC_HOLD_MS, 1.0)

        # At M0 the ring sat on an empty screen; it now has to read over bright cards,
        # so the scene dims as the hold advances. It also tells the grown-up which way
        # this is going, and vanishes the instant they let go.
        scrim = QColor(RING_SCRIM)
        scrim.setAlphaF(0.55 * progress)
        painter.fillRect(scene_rect, scrim)

        pen = QPen(
            RING_TRACK,
            diameter * RING_THICKNESS,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.drawEllipse(ring)  # track from the first frame, so it reacts at once

        pen.setColor(RING)
        painter.setPen(pen)
        painter.drawArc(ring, 90 * 16, -int(360 * 16 * progress))  # clockwise from 12
