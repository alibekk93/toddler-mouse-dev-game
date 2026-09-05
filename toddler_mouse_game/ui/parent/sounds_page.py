"""The Sounds page (SPEC §4.3): three lists and the recording dialog they share.

The Questions list groups by tag and says how many ways of asking each tag has, because
one clip per tag risks her learning to recognise two seconds of audio rather than the word
inside it (SPEC §2.1). Keeping a recording therefore does **not** close the dialog: the
offered next action is another phrasing of the same question.

The record dialog plays back the *normalised* clip — trimmed and levelled — so the trim is
judged by ear before anything is kept, which is the whole reason DATA_MODEL §8's audio
pipeline waited for this milestone.
"""

import wave
from array import array
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...audio import player as player_mod
from ...audio import recorder as recorder_mod
from ...core import library as library_mod
from ...core.importer import ImportRejected, to_int16
from ...core.library import Library
from ...core.models import Sound, normalise_tag

KINDS = (("question", "Questions"), ("praise", "Praise"), ("retry", "Retry"))


def _read_samples(path: Path) -> array:
    """The normalised WAV as int16, for the waveform."""
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            return to_int16(frames, handle.getsampwidth(), handle.getnchannels())
    except (OSError, wave.Error):
        return array("h")


def _describe(sound: Sound) -> str:
    text = sound.label or "(no label)"
    if sound.duration_ms:
        text += f"  ·  {sound.duration_ms / 1000:.1f}s"
    if not sound.enabled:
        text += "  ·  turned off"
    if sound.broken:
        text += "  ·  file missing"
    return text


# -- waveform --------------------------------------------------------------


class _Waveform(QWidget):
    """A peak envelope of the take. Enough to see that a word is actually in there."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(72)
        self._samples: array = array("h")

    def set_samples(self, samples: array) -> None:
        self._samples = samples
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f4f2ee"))
        if not self._samples:
            return
        middle = self.height() / 2
        columns = max(1, self.width())
        per_column = max(1, len(self._samples) // columns)
        painter.setPen(QPen(QColor("#3d6fd9"), 1))
        for x in range(columns):
            chunk = self._samples[x * per_column : (x + 1) * per_column]
            if not chunk:
                break
            peak = max(abs(value) for value in chunk) / 32768
            painter.drawLine(x, int(middle - peak * middle), x, int(middle + peak * middle))


# -- the record dialog -----------------------------------------------------


class RecordDialog(QDialog):
    """One sitting at the microphone. Several recordings can be kept without closing."""

    def __init__(self, kind: str, library: Library, save, player, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._library = library
        self._save = save
        self._player = player
        self._take: Path | None = None
        self.kept = 0

        self.setWindowTitle(
            {
                "question": "Record a question",
                "praise": "Record praise",
                "retry": "Record a retry line",
            }[kind]
        )
        self.resize(460, 460)
        self._build()

        self._recorder = recorder_mod.Recorder(self)
        self._recorder.level.connect(self._on_level)
        self._recorder.finished.connect(self._on_take)
        self._recorder.failed.connect(self._fail)
        # QDialog.finished covers every way out — Done, Esc, and the window's close
        # button. `accept()` alone never reaches closeEvent, which would leave the
        # microphone open and the scratch takes on disk.
        self.finished.connect(self._close_recorder)

        reason = recorder_mod.unavailable_reason()
        if reason:
            # SPEC §6: no microphone disables recording and says so plainly. Importing
            # an existing file still works, from the button on the page behind this.
            self._record.setEnabled(False)
            self._status.setText(reason)
        self._show_state("idle")

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        if self._kind == "question":
            tag_row = QHBoxLayout()
            tag_row.addWidget(QLabel("This asks for the tag:"))
            self._tag = QLineEdit()
            self._tag.setPlaceholderText("cat")
            completer = QCompleter(library_mod.all_tags(self._library), self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._tag.setCompleter(completer)
            self._tag.textChanged.connect(self._sync_keep)
            tag_row.addWidget(self._tag, 1)
            layout.addLayout(tag_row)
        else:
            self._tag = None

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Label:"))
        self._label = QLineEdit()
        self._label.setPlaceholderText("Where is the cat?")
        label_row.addWidget(self._label, 1)
        layout.addLayout(label_row)

        self._record = QPushButton("●")
        self._record.setFixedSize(96, 96)
        self._record.setStyleSheet(
            "QPushButton { border-radius: 48px; background: #d64a3d; color: white;"
            " font-size: 34px; } QPushButton:disabled { background: #bbb; }"
        )
        self._record.clicked.connect(self._toggle_recording)
        centred = QHBoxLayout()
        centred.addStretch(1)
        centred.addWidget(self._record)
        centred.addStretch(1)
        layout.addLayout(centred)

        self._meter = QProgressBar()
        self._meter.setRange(0, 100)
        self._meter.setTextVisible(False)
        self._meter.setFixedHeight(12)
        layout.addWidget(self._meter)

        self._wave = _Waveform()
        layout.addWidget(self._wave)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)
        layout.addStretch(1)

        row = QHBoxLayout()
        self._play = QPushButton("Play")
        self._play.clicked.connect(lambda: self._player.play_voice(self._take))
        self._again = QPushButton("Re-record")
        self._again.clicked.connect(self._toggle_recording)
        self._keep = QPushButton("Keep")
        self._keep.setDefault(True)
        self._keep.clicked.connect(self._keep_take)
        done = QPushButton("Done")
        done.clicked.connect(self.accept)
        for button in (self._play, self._again, self._keep):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(done)
        layout.addLayout(row)

    # -- state -------------------------------------------------------------

    def _show_state(self, state: str) -> None:
        recording = state == "recording"
        reviewing = state == "review"
        self._record.setText("■" if recording else "●")
        self._record.setVisible(not reviewing)
        for button in (self._play, self._again, self._keep):
            button.setVisible(reviewing)
        if reviewing:
            self._sync_keep()

    def _sync_keep(self) -> None:
        """A question needs its tag before it can be kept (SPEC §5)."""
        needs_tag = self._tag is not None and not self._tag.text().strip()
        self._keep.setEnabled(not needs_tag)
        self._keep.setToolTip("Type the tag this question asks for" if needs_tag else "")

    def _toggle_recording(self) -> None:
        if self._recorder.is_recording():
            self._recorder.stop()
            self._status.setText("Trimming…")
            return
        self._take = None
        self._wave.set_samples(array("h"))
        if self._recorder.start():
            self._show_state("recording")
            self._status.setText("Recording — press again to stop (stops on its own at 10s).")

    def _on_level(self, level: float) -> None:
        self._meter.setValue(int(level * 100))

    def _on_take(self, path: Path) -> None:
        self._take = path
        self._wave.set_samples(_read_samples(path))
        self._show_state("review")
        self._status.setText("Trimmed and levelled. Have a listen before you keep it.")
        self._player.play_voice(path)

    def _fail(self, message: str) -> None:
        self._show_state("idle")
        self._status.setText(message)

    def _keep_take(self) -> None:
        tag = normalise_tag(self._tag.text()) if self._tag is not None else None
        try:
            library_mod.add_sound(
                self._library,
                self._take,
                self._kind,
                target_tag=tag,
                label=self._label.text().strip() or None,
            )
        except ImportRejected as exc:
            self._status.setText(str(exc))
            return

        self.kept += 1
        self._save()
        self._take = None
        self._label.clear()
        self._wave.set_samples(array("h"))
        self._show_state("idle")
        # SPEC §4.3: the offered next action is another phrasing, not closing the dialog.
        self._status.setText(
            f"Kept. Now record another way of asking for '{tag}' — three phrasings is a "
            "good target."
            if tag
            else "Kept. Record another?"
        )

    def _close_recorder(self) -> None:
        self._recorder.cleanup()
        self._player.stop_voice()


# -- the page --------------------------------------------------------------


class SoundsPage(QWidget):
    """Questions, Praise, and Retry, each with a record button and a file importer."""

    def __init__(self, library: Library, save) -> None:
        super().__init__()
        self._library = library
        self._save = save
        self._player = player_mod.Player()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._tabs = QTabWidget()
        self._questions = QTreeWidget()
        self._questions.setHeaderLabels(["Question", ""])
        self._questions.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tabs.addTab(self._questions, "Questions")
        self._lists = {}
        for kind, title in KINDS[1:]:
            view = QListWidget()
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self._lists[kind] = view
            self._tabs.addTab(view, title)
        layout.addWidget(self._tabs, 1)

        row = QHBoxLayout()
        record = QPushButton("Record…")
        record.clicked.connect(self._record)
        row.addWidget(record)
        import_file = QPushButton("Import a sound file…")
        import_file.clicked.connect(self._import_file)
        row.addWidget(import_file)
        row.addStretch(1)
        for text, slot in (
            ("Play", self._play),
            ("Edit label…", self._edit_label),
            ("Enable / disable", self._toggle_enabled),
            ("Delete", self._delete),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        layout.addLayout(row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)

        self.reload()

    # -- reading the library -----------------------------------------------

    def reload(self) -> None:
        self._questions.clear()
        questions = [s for s in self._library.sounds if s.kind == "question"]
        by_tag: dict[str, list[Sound]] = {}
        for sound in questions:
            by_tag.setdefault(sound.target_tag or "(no tag)", []).append(sound)

        for tag in sorted(by_tag):
            group = by_tag[tag]
            ways = "1 way of asking" if len(group) == 1 else f"{len(group)} ways of asking"
            parent = QTreeWidgetItem([tag, ways])
            if len(group) == 1:
                # A gentle nudge, not a warning: one clip per tag is playable, just weaker.
                parent.setForeground(1, QColor("#b07a2a"))
            for sound in group:
                child = QTreeWidgetItem([_describe(sound), ""])
                child.setData(0, Qt.ItemDataRole.UserRole, sound.id)
                parent.addChild(child)
            self._questions.addTopLevelItem(parent)
        self._questions.expandAll()
        self._questions.resizeColumnToContents(0)

        for kind, view in self._lists.items():
            view.clear()
            for sound in self._library.sounds:
                if sound.kind != kind:
                    continue
                item = QListWidgetItem(_describe(sound))
                item.setData(Qt.ItemDataRole.UserRole, sound.id)
                view.addItem(item)

    def _kind(self) -> str:
        return KINDS[self._tabs.currentIndex()][0]

    def _selected(self) -> list[Sound]:
        if self._tabs.currentIndex() == 0:
            items = self._questions.selectedItems()
            ids = {i.data(0, Qt.ItemDataRole.UserRole) for i in items}
        else:
            view = self._lists[self._kind()]
            ids = {i.data(Qt.ItemDataRole.UserRole) for i in view.selectedItems()}
        return [s for s in self._library.sounds if s.id in ids]

    # -- adding ------------------------------------------------------------

    def _record(self) -> None:
        dialog = RecordDialog(self._kind(), self._library, self._save, self._player, self)
        dialog.exec()
        self.reload()
        if dialog.kept:
            self._status.setText(f"Kept {dialog.kept} recording(s).")

    def _import_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Import a sound", "", "Sounds (*.wav)")
        if not path:
            return
        tag = None
        if self._kind() == "question":
            tag, ok = QInputDialog.getItem(
                self,
                "Question tag",
                "Which tag does this question ask for?",
                library_mod.all_tags(self._library),
                0,
                True,
            )
            if not ok or not tag.strip():
                return
        try:
            library_mod.add_sound(
                self._library, Path(path), self._kind(), target_tag=tag, label=Path(path).stem
            )
        except ImportRejected as exc:
            self._status.setText(str(exc))
            return
        self._save()
        self.reload()
        self._status.setText(f"Imported {Path(path).name}.")

    # -- per-row actions ---------------------------------------------------

    def _play(self) -> None:
        selected = self._selected()
        if not selected:
            return
        if not player_mod.AVAILABLE:
            self._status.setText(f"Audio is unavailable here: {player_mod.UNAVAILABLE_REASON}")
            return
        self._player.play_voice(Path(self._library.root) / selected[0].file)

    def _edit_label(self) -> None:
        selected = self._selected()
        if not selected:
            return
        text, ok = QInputDialog.getText(
            self,
            "Label",
            "What does this recording say?",
            QLineEdit.EchoMode.Normal,
            selected[0].label or "",
        )
        if not ok:
            return
        for sound in selected:
            sound.label = text.strip() or None
        self._save()
        self.reload()

    def _toggle_enabled(self) -> None:
        selected = self._selected()
        if not selected:
            return
        target = not all(sound.enabled for sound in selected)
        for sound in selected:
            sound.enabled = target
        self._save()
        self.reload()

    def _delete(self) -> None:
        selected = self._selected()
        if not selected:
            return
        confirm = QMessageBox.question(
            self,
            "Delete recordings",
            f"Move {len(selected)} recording(s) to the library's _trash folder?\n"
            "Nothing is erased — a parent's voice is the hardest thing here to replace.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for sound in selected:
            library_mod.remove_sound(self._library, sound)
        self._save()
        self.reload()
        self._status.setText(f"Moved {len(selected)} recording(s) to _trash.")
