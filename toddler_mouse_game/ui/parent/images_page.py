"""The Pictures page (SPEC §4.2): a thumbnail grid, three ways in, and a staging tray.

Two rules shape this file.

**Tags are only ever typed by a parent.** Nothing here reads a filename, a folder name, or
any metadata to guess what a picture is of. Imports land untagged in the staging tray and
join the library only once someone has typed something.

**Nothing blocks the window.** Twelve pasted photos are twelve decode-and-resize jobs, so
they run on `QThreadPool` and report back by signal (ARCHITECTURE §4.5).
"""

import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
from ...core.importer import ImportRejected, import_image
from ...core.library import IMAGE_SUFFIXES, Library
from ...core.models import Image, normalise_tags

THUMB = QSize(140, 140)


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

    def __init__(self, library: Library, save) -> None:
        super().__init__()
        self._library = library
        self._save = save
        self._pending: list[Image] = []
        self._pending_tags: dict[str, list[str]] = {}
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
        self._selection_buttons = []
        for text, slot in (
            ("Edit tags…", self._edit_tags),
            ("Set category…", self._edit_category),
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
        inner.addWidget(self._tray_grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("Tags:"))
        self._tags_field = QLineEdit()
        self._tags_field.setPlaceholderText("comma-separated, any language: cat, animal / кошка")
        self._tags_field.returnPressed.connect(self._apply_tags)
        row.addWidget(self._tags_field, 2)
        row.addWidget(QLabel("Category:"))
        self._category_field = QLineEdit()
        self._category_field.setPlaceholderText("optional: animals")
        row.addWidget(self._category_field, 1)
        inner.addLayout(row)

        buttons = QHBoxLayout()
        apply_to = QPushButton("Apply tags to selected")
        apply_to.setToolTip("Tag part of the tray differently — twelve dogs and three cats.")
        apply_to.clicked.connect(self._apply_tags)
        buttons.addWidget(apply_to)
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
            QThreadPool.globalInstance().start(lambda p=path: self._import_one(p, source))

    def _import_one(self, path: Path, source: str) -> None:
        """Worker thread: decode, downscale, thumbnail, write. No manifest touching."""
        try:
            entry = import_image(path, self._library.root, source=source)
        except ImportRejected as exc:
            self._rejected.emit(str(exc))
            return
        self._imported.emit(entry)

    # -- the staging tray --------------------------------------------------

    def _on_imported(self, entry: Image) -> None:
        if any(pending.id == entry.id for pending in self._pending):
            return  # the same file dropped twice in one batch
        existing = self._library.image_by_id(entry.id)
        if existing is not None:
            # Same content hash: this picture is already here. Its tray tags start from
            # the ones it already has, so adding merges rather than duplicating.
            self._pending_tags[entry.id] = list(existing.tags)
        self._pending.append(entry)
        self._reload_tray()
        self._tags_field.setFocus()

    def _reload_tray(self) -> None:
        self._tray_grid.clear()
        for entry in self._pending:
            tags = self._pending_tags.get(entry.id, [])
            item = QListWidgetItem(", ".join(tags) or "(needs tags)")
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setIcon(QIcon(str(Path(self._library.root) / entry.thumb)))
            self._tray_grid.addItem(item)
        self._tray.setVisible(bool(self._pending))
        self._tray.setTitle(f"{len(self._pending)} new picture(s) — type their tags")

    def _apply_tags(self) -> None:
        """Bulk tagging: the field applies to the selection, or to everything."""
        tags = normalise_tags(self._tags_field.text().split(","))
        if not tags:
            return
        chosen = {i.data(Qt.ItemDataRole.UserRole) for i in self._tray_grid.selectedItems()}
        for entry in self._pending:
            if not chosen or entry.id in chosen:
                self._pending_tags[entry.id] = tags
        self._tags_field.clear()
        self._reload_tray()

    def _commit_pending(self) -> None:
        """Anything still untagged takes whatever is in the field on the way in."""
        fallback = normalise_tags(self._tags_field.text().split(","))
        category = self._category_field.text().strip() or None
        for entry in self._pending:
            tags = self._pending_tags.get(entry.id) or fallback
            library_mod.attach_image(self._library, entry, tags, category)

        count = len(self._pending)
        self._discard_pending()
        self._save()
        self.reload()
        self._note(f"Added {count} picture(s).")

    def _discard_pending(self) -> None:
        """Clears the tray. The normalised files stay on disk — validation offers to
        adopt them later (DATA_MODEL §4), and nothing here deletes a parent's picture."""
        self._pending.clear()
        self._pending_tags.clear()
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
        current = selected[0].category or ""
        text, ok = QInputDialog.getText(
            self,
            "Category",
            f"Category for {len(selected)} picture(s) (blank for none):",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        for image in selected:
            image.category = text.strip() or None
        self._save()
        self.reload()

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
