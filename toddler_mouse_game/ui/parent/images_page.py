"""The Pictures page (SPEC §4.2): a thumbnail grid, three ways in, and a staging tray.

Two rules shape this file.

**Tags are only ever typed by a parent.** Nothing here reads a filename, a folder name, or
any metadata to guess what a picture is of. Imports land untagged in the staging tray and
join the library only once someone has typed something.

**Nothing blocks the window.** Twelve pasted photos are twelve decode-and-resize jobs, so
they run on `QThreadPool` and report back by signal (ARCHITECTURE §4.5).
"""

import hashlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import library as library_mod
from ...core.importer import ImportRejected, normalise_image, write_image
from ...core.library import IMAGE_SUFFIXES, Library
from ...core.models import Image, Settings, normalise_tags
from .crop_dialog import CropDialog

THUMB = QSize(140, 140)


@dataclass
class _Pending:
    """A picture normalised but not yet written: what the staging tray holds.

    Keyed by `seq`, not by content hash, so a re-crop replaces the tray entry it came
    from even though its bytes — and therefore its future id — have changed.
    """

    seq: int
    source: Path
    origin: str  # file | drop | clipboard
    data: bytes
    thumb: bytes
    extension: str
    width: int
    height: int
    digest: str
    crop: tuple | None = None
    tags: list[str] = field(default_factory=list)


def _grid(selectable: bool = True) -> QListWidget:
    """A thumbnail grid. `QListWidget` in icon mode is the free version of one."""
    view = QListWidget()
    view.setViewMode(QListWidget.ViewMode.IconMode)
    view.setIconSize(THUMB)
    view.setGridSize(QSize(THUMB.width() + 30, THUMB.height() + 46))
    view.setResizeMode(QListWidget.ResizeMode.Adjust)
    view.setMovement(QListWidget.Movement.Static)
    view.setWordWrap(True)
    view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)  # drops go to the page
    if selectable:
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    return view


class ImagesPage(QWidget):
    """Grid of what's in the library, plus a tray of what's on its way in."""

    _imported = Signal(object)  # an untagged Image, from a worker thread
    _rejected = Signal(str)

    def __init__(self, library: Library, settings: Settings, save, save_settings) -> None:
        super().__init__()
        self._library = library
        self._settings = settings
        self._save = save
        self._save_settings = save_settings
        self._pending: list[_Pending] = []
        self._sequence = 0
        self._scratch = tempfile.TemporaryDirectory(prefix="buska-paste-")
        self._pastes = 0

        self.setAcceptDrops(True)
        self._build()

        self._imported.connect(self._on_imported)
        self._rejected.connect(self._note)
        QShortcut(QKeySequence.StandardKey.Paste, self, self._paste)
        self.reload()

    # -- layout ------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        add = QPushButton("Add pictures…")
        add.clicked.connect(self._choose_files)
        top.addWidget(add)
        top.addWidget(QLabel("or drag them in, or paste with Ctrl+V"))
        top.addStretch(1)
        matching = QPushButton("Category matching…")
        matching.setToolTip("Which categories may only be compared with their own kind")
        matching.clicked.connect(self._edit_strict_categories)
        top.addWidget(matching)
        self._selection_buttons = []
        for text, slot in (
            ("Edit tags…", self._edit_tags),
            ("Categories…", self._edit_category),
            ("Enable / disable", self._toggle_enabled),
            ("Delete", self._delete),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            top.addWidget(button)
            self._selection_buttons.append(button)
        layout.addLayout(top)

        self._grid = _grid()
        self._grid.itemSelectionChanged.connect(self._sync_buttons)
        self._grid.itemDoubleClicked.connect(lambda _item: self._edit_tags())
        layout.addWidget(self._grid, 1)

        self._tray = self._build_tray()
        layout.addWidget(self._tray)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)

    def _build_tray(self) -> QGroupBox:
        """The staging tray: nothing joins the library until the tags are typed."""
        box = QGroupBox("New pictures — type their tags before adding them")
        box.setVisible(False)
        inner = QVBoxLayout(box)

        self._tray_grid = _grid()
        self._tray_grid.setFixedHeight(THUMB.height() + 70)
        self._tray_grid.itemSelectionChanged.connect(self._sync_tray_buttons)
        inner.addWidget(self._tray_grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("Tags:"))
        self._tags_field = QLineEdit()
        self._tags_field.setPlaceholderText("comma-separated, any language: cat, animal / кошка")
        self._tags_field.returnPressed.connect(self._apply_tags)
        row.addWidget(self._tags_field, 2)
        row.addWidget(QLabel("Categories:"))
        self._category_field = QLineEdit()
        self._category_field.setPlaceholderText("optional: colours, shapes")
        row.addWidget(self._category_field, 1)
        inner.addLayout(row)

        buttons = QHBoxLayout()
        apply_to = QPushButton("Apply tags to selected")
        apply_to.setToolTip("Tag part of the tray differently — twelve dogs and three cats.")
        apply_to.clicked.connect(self._apply_tags)
        buttons.addWidget(apply_to)
        self._crop_button = QPushButton("Crop…")
        self._crop_button.setToolTip("Cut a picture down to the part that matters")
        self._crop_button.clicked.connect(self._crop_selected)
        buttons.addWidget(self._crop_button)
        buttons.addStretch(1)
        discard = QPushButton("Discard")
        discard.clicked.connect(self._discard_pending)
        buttons.addWidget(discard)
        add = QPushButton("Add to library")
        add.setDefault(True)
        add.clicked.connect(self._commit_pending)
        buttons.addWidget(add)
        inner.addLayout(buttons)
        return box

    # -- reading the library -----------------------------------------------

    def reload(self) -> None:
        self._grid.clear()
        for entry in self._library.images:
            item = QListWidgetItem(self._caption(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setIcon(QIcon(str(Path(self._library.root) / entry.thumb)))
            if entry.broken or not entry.enabled:
                item.setForeground(Qt.GlobalColor.gray)
            self._grid.addItem(item)
        self._sync_buttons()

    def _caption(self, entry: Image) -> str:
        if entry.broken:
            return "(file missing)"
        text = ", ".join(entry.tags) or "(no tags yet)"
        return text if entry.enabled else f"{text}\n(turned off)"

    def _selected(self) -> list[Image]:
        ids = {i.data(Qt.ItemDataRole.UserRole) for i in self._grid.selectedItems()}
        return [image for image in self._library.images if image.id in ids]

    def _sync_buttons(self) -> None:
        for button in self._selection_buttons:
            button.setEnabled(bool(self._grid.selectedItems()))

    def _note(self, message: str) -> None:
        self._status.setText(message)

    # -- the three ways in (SPEC §4.2) -------------------------------------

    def _choose_files(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(IMAGE_SUFFIXES))
        paths, _filter = QFileDialog.getOpenFileNames(
            self, "Add pictures", "", f"Pictures ({patterns})"
        )
        self._import([Path(p) for p in paths], "file")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        event.acceptProposedAction()
        self._import(paths, "drop")

    def _paste(self) -> None:
        mime = QApplication.clipboard().mimeData()
        if mime.hasImage():
            image = QImage(mime.imageData())
            if not image.isNull():
                self._pastes += 1
                path = Path(self._scratch.name) / f"paste-{self._pastes}.png"
                image.save(str(path), "PNG")
                self._import([path], "clipboard")
                return
        if mime.hasUrls():
            # Local files only. A remote URL on the clipboard is ignored, never fetched:
            # this app makes no network calls (ARCHITECTURE §4.4, CLAUDE.md rule 2).
            local = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
            if local:
                self._import(local, "clipboard")
                return
        self._note("Nothing on the clipboard that looks like a picture.")

    def _import(self, paths: list[Path], source: str) -> None:
        wanted = [p for p in paths if p.suffix.lower() in IMAGE_SUFFIXES]
        skipped = len(paths) - len(wanted)
        if not wanted:
            self._note("No pictures in that — only image files can be added." if paths else "")
            return
        self._note(
            f"Adding {len(wanted)} picture(s)…" + (f" ({skipped} skipped)" if skipped else "")
        )
        for path in wanted:
            self._sequence += 1
            self._normalise(self._sequence, path, source)

    def _normalise(self, seq: int, path: Path, source: str, crop=None) -> None:
        QThreadPool.globalInstance().start(lambda: self._normalise_one(seq, path, source, crop))

    def _normalise_one(self, seq: int, path: Path, source: str, crop) -> None:
        """Worker thread: decode, crop, downscale, thumbnail. Writes nothing.

        The file lands on disk only when the parent presses Add to library, which is what
        makes cropping free — and what makes Discard a true discard, with no half-imported
        picture left behind for validation to find later.
        """
        try:
            data, thumb, extension, width, height = normalise_image(path, crop=crop)
        except ImportRejected as exc:
            self._rejected.emit(str(exc))
            return
        self._imported.emit(
            _Pending(
                seq=seq,
                source=Path(path),
                origin=source,
                data=data,
                thumb=thumb,
                extension=extension,
                width=width,
                height=height,
                digest=hashlib.sha256(data).hexdigest(),
                crop=crop,
            )
        )

    # -- the staging tray --------------------------------------------------

    def _on_imported(self, pending: "_Pending") -> None:
        replacing = next((p for p in self._pending if p.seq == pending.seq), None)
        if replacing is not None:  # a re-crop of something already in the tray
            pending.tags = replacing.tags
            self._pending[self._pending.index(replacing)] = pending
        else:
            if any(p.digest == pending.digest for p in self._pending):
                return  # the same file dropped twice in one batch
            existing = self._existing_for(pending.digest)
            if existing is not None:
                # Same content hash: this picture is already here. Its tray tags start
                # from the ones it has, so adding merges rather than duplicating.
                pending.tags = list(existing.tags)
            self._pending.append(pending)
        self._reload_tray()
        self._tags_field.setFocus()

    def _existing_for(self, digest: str) -> Image | None:
        """The library entry for these bytes, if there is one.

        Matched by prefix rather than equality: an id is normally the first 8 hex chars
        of the digest but extends on a genuine collision (DATA_MODEL §3).
        """
        return next((i for i in self._library.images if digest.startswith(i.id)), None)

    def _reload_tray(self) -> None:
        self._tray_grid.clear()
        for pending in self._pending:
            caption = ", ".join(pending.tags) or "(needs tags)"
            item = QListWidgetItem(f"{caption}\n(cropped)" if pending.crop else caption)
            item.setData(Qt.ItemDataRole.UserRole, pending.seq)
            pixmap = QPixmap()
            pixmap.loadFromData(pending.thumb)
            item.setIcon(QIcon(pixmap))
            self._tray_grid.addItem(item)
        self._tray.setVisible(bool(self._pending))
        self._tray.setTitle(f"{len(self._pending)} new picture(s) — type their tags")
        self._sync_tray_buttons()

    def _selected_pending(self) -> list["_Pending"]:
        chosen = {i.data(Qt.ItemDataRole.UserRole) for i in self._tray_grid.selectedItems()}
        return [p for p in self._pending if p.seq in chosen]

    def _sync_tray_buttons(self) -> None:
        self._crop_button.setEnabled(len(self._selected_pending()) == 1)

    def _crop_selected(self) -> None:
        """Crop before the picture joins the library, never after: the id is the hash of
        the normalised bytes, so a crop applied later would be a different picture."""
        chosen = self._selected_pending()
        if len(chosen) != 1:
            return
        pending = chosen[0]
        dialog = CropDialog(pending.source, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # Esc or the close button: leave an existing crop alone
        if dialog.box is not None:
            self._note("Cropping…")
            self._normalise(pending.seq, pending.source, pending.origin, crop=dialog.box)
        elif dialog.reset and pending.crop is not None:
            self._note("Using the whole picture…")
            self._normalise(pending.seq, pending.source, pending.origin)

    def _apply_tags(self) -> None:
        """Bulk tagging: the field applies to the selection, or to everything."""
        tags = normalise_tags(self._tags_field.text().split(","))
        if not tags:
            return
        chosen = {p.seq for p in self._selected_pending()}
        for pending in self._pending:
            if not chosen or pending.seq in chosen:
                pending.tags = tags
        self._tags_field.clear()
        self._reload_tray()

    def _commit_pending(self) -> None:
        """Write the files, then the manifest. Anything still untagged takes whatever is
        in the field on the way in."""
        fallback = normalise_tags(self._tags_field.text().split(","))
        categories = normalise_tags(self._category_field.text().split(","))
        for pending in self._pending:
            entry = write_image(
                self._library.root,
                pending.data,
                pending.thumb,
                pending.extension,
                pending.width,
                pending.height,
                source=pending.origin,
            )
            library_mod.attach_image(self._library, entry, pending.tags or fallback, categories)

        count = len(self._pending)
        self._discard_pending()
        self._save()
        self.reload()
        self._note(f"Added {count} picture(s).")

    def _discard_pending(self) -> None:
        """Clears the tray. Nothing was written, so nothing is left behind."""
        self._pending.clear()
        self._tags_field.clear()
        self._category_field.clear()
        self._reload_tray()

    # -- per-image actions -------------------------------------------------

    def _edit_tags(self) -> None:
        selected = self._selected()
        if not selected:
            return
        current = ", ".join(selected[0].tags) if len(selected) == 1 else ""
        text, ok = QInputDialog.getText(
            self,
            "Tags",
            f"Comma-separated tags for {len(selected)} picture(s):",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        for image in selected:
            image.tags = normalise_tags(text.split(","))
        self._save()
        self.reload()

    def _edit_category(self) -> None:
        selected = self._selected()
        if not selected:
            return
        current = ", ".join(selected[0].categories) if len(selected) == 1 else ""
        text, ok = QInputDialog.getText(
            self,
            "Categories",
            f"Comma-separated categories for {len(selected)} picture(s), blank for none.\n"
            "A picture can be in several: a yellow square is a colour and a shape.",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        for image in selected:
            image.categories = normalise_tags(text.split(","))
        self._save()
        self.reload()

    def _edit_strict_categories(self) -> None:
        """Which categories may only be compared with their own kind.

        Tags say what a picture is *of*; nothing says what it incidentally looks like, so
        a dog tagged only `dog` can still be yellow and turn up as a wrong-but-not-wrong
        answer to "where is yellow?". Ticking `colours` here keeps colour questions among
        colour pictures, and leaves "where is the cat" free to show a truck.
        """
        known = sorted({c for image in self._library.images for c in image.categories})
        if not known:
            self._note("No categories yet — give some pictures a category first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Category matching")
        layout = QVBoxLayout(dialog)
        caption = QLabel(
            "Tick a category to compare it only with itself.\n\n"
            "Use it for categories a picture can accidentally belong to — colours, sizes.\n"
            "A yellow-ish dog should never be the wrong answer to “where is yellow?”."
        )
        caption.setWordWrap(True)
        layout.addWidget(caption)

        strict = set(self._settings.strict_categories)
        boxes = {}
        for category in known:
            box = QCheckBox(category)
            box.setChecked(category in strict)
            layout.addWidget(box)
            boxes[category] = box

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Categories ticked before but no longer in the library are kept: a category can
        # come back when its pictures do, and silently forgetting the choice is worse.
        gone = strict - set(known)
        self._settings.strict_categories = sorted(
            gone | {name for name, box in boxes.items() if box.isChecked()}
        )
        self._save_settings()
        chosen = [name for name, box in boxes.items() if box.isChecked()]
        self._note(
            f"Matched only within: {', '.join(chosen)}." if chosen else "No category is strict."
        )

    def _toggle_enabled(self) -> None:
        selected = self._selected()
        if not selected:
            return
        target = not all(image.enabled for image in selected)
        for image in selected:
            image.enabled = target
        self._save()
        self.reload()

    def _delete(self) -> None:
        selected = self._selected()
        if not selected:
            return
        confirm = QMessageBox.question(
            self,
            "Delete pictures",
            f"Move {len(selected)} picture(s) to the library's _trash folder?\n"
            "Nothing is erased — the files stay on disk and can be moved back.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for image in selected:
            library_mod.remove_image(self._library, image)
        self._save()
        self.reload()
        self._note(f"Moved {len(selected)} picture(s) to _trash.")
