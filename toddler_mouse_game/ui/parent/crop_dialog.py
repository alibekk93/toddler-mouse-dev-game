"""Drag a rectangle over a picture before it joins the library (SPEC §4.2).

A photo where the cat is a small part of a busy kitchen makes a bad card: the card
letterboxes the picture whole (UX §1), so the subject ends up tiny on a screen a
two-year-old is looking at from across a table.

The dialog returns a **fractional** box, not pixels, so the preview can be any size and
the crop still applies to the full-resolution original. It runs before anything is
written, so cropping costs nothing and can be redone as often as the parent likes.
"""

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRubberBand,
    QVBoxLayout,
)

PREVIEW_EDGE = 640
MIN_DRAG = 12  # px in the preview; below this it was a click, not a crop


def _load(source: Path) -> QPixmap:
    """Read the picture the way `core.importer` will: EXIF orientation applied.

    Qt does not auto-transform by default, and a preview rotated differently from what
    the importer crops would silently take the wrong region of a phone photo.
    """
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    image = reader.read()
    return QPixmap.fromImage(image) if not image.isNull() else QPixmap()


class _Canvas(QLabel):
    """The preview, sized to exactly its pixmap so widget coords are pixmap coords."""

    def __init__(self, pixmap: QPixmap) -> None:
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._origin = None
        self.on_change = lambda: None

    def mousePressEvent(self, event) -> None:
        self._origin = event.position().toPoint()
        self._band.setGeometry(QRect(self._origin, QSize()))
        self._band.show()
        self.on_change()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is None:
            return
        corner = event.position().toPoint()
        self._band.setGeometry(QRect(self._origin, corner).normalized() & self.rect())
        self.on_change()

    def mouseReleaseEvent(self, _event) -> None:
        self._origin = None
        self.on_change()

    def selection(self) -> QRect:
        return self._band.geometry() if self._band.isVisible() else QRect()

    def fractions(self):
        """The selection as (left, top, right, bottom) in 0..1, or None."""
        rect = self.selection() & self.rect()
        if rect.width() < MIN_DRAG or rect.height() < MIN_DRAG:
            return None
        width, height = self.width(), self.height()
        return (
            rect.left() / width,
            rect.top() / height,
            rect.right() / width,
            rect.bottom() / height,
        )


class CropDialog(QDialog):
    """`exec()`, then read the outcome.

    Accepted with `box` set means crop to that fraction. Accepted with `reset` means the
    parent asked for the whole picture back. Rejected — Esc, or the window's close button
    — means leave it exactly as it was, which for an already-cropped picture must *not*
    quietly undo the crop.
    """

    def __init__(self, source: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crop")
        self.box = None
        self.reset = False

        layout = QVBoxLayout(self)
        pixmap = _load(Path(source))
        if pixmap.isNull():
            layout.addWidget(QLabel("This picture cannot be previewed, so it cannot be cropped."))
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            self._canvas = None
            return

        scaled = pixmap.scaled(
            PREVIEW_EDGE,
            PREVIEW_EDGE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._canvas = _Canvas(scaled)
        self._canvas.on_change = self._sync
        layout.addWidget(self._canvas, 0, Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Drag a rectangle over the part that matters.")
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        whole = QPushButton("Use the whole picture")
        whole.clicked.connect(self._use_whole)
        row.addWidget(whole)
        row.addStretch(1)
        self._crop = QPushButton("Crop")
        self._crop.setDefault(True)
        self._crop.clicked.connect(self._accept_crop)
        row.addWidget(self._crop)
        layout.addLayout(row)
        self._sync()

    def _sync(self) -> None:
        self._crop.setEnabled(self._canvas.fractions() is not None)

    def _accept_crop(self) -> None:
        self.box = self._canvas.fractions()
        if self.box is not None:
            self.accept()

    def _use_whole(self) -> None:
        self.box = None
        self.reset = True
        self.accept()
