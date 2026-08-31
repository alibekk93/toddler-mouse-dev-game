"""Load, save, validate, and repair a library folder. Pure Python — no Qt.

Two principles from DATA_MODEL §1 drive everything here: the manifest is an index but
**the disk is the truth**, and nothing is ever destructive. A corrupt `library.json` is
repaired from `.bak` or rebuilt by scanning the folder — it is never overwritten with
an empty library on top of a folder full of content (CLAUDE.md rule 5).
"""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .importer import AUDIO_DIRS, adopt_audio, import_image
from .models import Image, Sound, normalise_tag, normalise_tags, utc_now

SCHEMA_VERSION = 1
MANIFEST = "library.json"
BACKUP = "library.json.bak"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass(slots=True)
class Issue:
    """One row of the DATA_MODEL §4 table: a warning with a concrete subject.

    `code` is what the parent UI maps to an offered action (Locate / Remove / Adopt /
    Merge). Every check yields one of these; none of them raises.
    """

    code: str
    message: str
    subject_id: str | None = None


@dataclass(slots=True)
class Library:
    root: Path
    images: list[Image] = field(default_factory=list)
    sounds: list[Sound] = field(default_factory=list)

    def image_by_id(self, image_id: str) -> Image | None:
        return next((i for i in self.images if i.id == image_id), None)

    def playable_images(self) -> list[Image]:
        return [i for i in self.images if i.enabled and not i.broken]

    def playable_sounds(self, kind: str) -> list[Sound]:
        return [s for s in self.sounds if s.kind == kind and s.enabled and not s.broken]


# -- reading ---------------------------------------------------------------


def _entry(cls, raw: dict):
    """Build a model from a manifest entry, ignoring keys we don't know."""
    known = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in raw.items() if k in known})


def _parse(root: Path, data: dict) -> tuple[Library, list[Issue]]:
    library = Library(root=root)
    issues: list[Issue] = []
    for key, cls, target in (
        ("images", Image, library.images),
        ("sounds", Sound, library.sounds),
    ):
        for raw in data.get(key, []) or []:
            try:
                entry = _entry(cls, raw)
            except (TypeError, ValueError):
                issues.append(Issue("unreadable_entry", f"skipped an unreadable {key[:-1]} entry"))
                continue
            if not entry.id or not entry.file:
                issues.append(Issue("unreadable_entry", f"skipped a {key[:-1]} entry with no id"))
                continue
            if isinstance(entry, Image):
                entry.tags = normalise_tags(entry.tags)
            else:
                entry.target_tag = normalise_tag(entry.target_tag) if entry.target_tag else None
            target.append(entry)
    return library, issues


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _scan_disk(root: Path) -> Library:
    """Rebuild from what is actually on disk. Everything is adopted untagged."""
    library = Library(root=root)
    for path in sorted((root / "images").glob("*")):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        thumb = root / "thumbs" / f"{path.stem}.jpg"
        library.images.append(
            Image(
                id=path.stem,
                file=f"images/{path.name}",
                thumb=f"thumbs/{path.stem}.jpg" if thumb.exists() else "",
            )
        )
    for kind, folder in AUDIO_DIRS.items():
        for path in sorted((root / folder).glob("*.wav")):
            # A rebuilt question has lost its target tag; validation reports it as
            # unusable rather than guessing one from the filename.
            library.sounds.append(Sound(id=path.stem, kind=kind, file=f"{folder}/{path.name}"))
    return library


def load(root: Path) -> tuple[Library, list[Issue]]:
    """Read the library at `root`, repairing as needed. Never raises, never empties."""
    root = Path(root)

    data = _read(root / MANIFEST)
    if data is not None:
        return _parse(root, data)

    manifest_existed = (root / MANIFEST).exists()

    data = _read(root / BACKUP)
    if data is not None:
        library, issues = _parse(root, data)
        return library, [
            Issue("restored_from_bak", "library.json was unreadable; used the backup")
        ] + issues

    library = _scan_disk(root)
    if manifest_existed or library.images or library.sounds:
        count = len(library.images) + len(library.sounds)
        return library, [
            Issue("rebuilt_from_disk", f"manifest unreadable; rebuilt from {count} files on disk")
        ]
    return library, []  # a genuinely empty folder is not a problem


# -- writing ---------------------------------------------------------------


def _serialise(entry) -> dict:
    """Manifest form: drop `broken` (recomputed from disk) and absent optionals."""
    return {k: v for k, v in asdict(entry).items() if k != "broken" and v is not None}


def save(library: Library) -> None:
    """DATA_MODEL §4 write protocol. A power cut mid-save must never lose the library."""
    root = Path(library.root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / MANIFEST
    tmp = root / (MANIFEST + ".tmp")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now(),
        "images": [_serialise(i) for i in library.images],
        "sounds": [_serialise(s) for s in library.sounds],
    }
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())

    if path.exists():
        os.replace(path, root / BACKUP)  # rotate the current good version
    os.replace(tmp, path)


# -- validation ------------------------------------------------------------


def enabled_tags(library: Library) -> set[str]:
    """Tags with at least one enabled, unbroken image behind them."""
    return {tag for image in library.playable_images() for tag in image.tags}


def validate(library: Library, option_count: int = 2) -> list[Issue]:
    """The DATA_MODEL §4 checks. Marks `broken`, and returns a warning per finding."""
    root = Path(library.root)
    issues: list[Issue] = []

    referenced: set[Path] = set()
    for entry in [*library.images, *library.sounds]:
        path = root / entry.file
        referenced.add(path)
        entry.broken = not path.is_file()
        if entry.broken:
            issues.append(Issue("missing_file", f"{entry.file} is missing from disk", entry.id))

    folders = ["images", *AUDIO_DIRS.values()]
    for folder in folders:
        for path in sorted((root / folder).glob("*")):
            if path.is_file() and path not in referenced:
                issues.append(Issue("orphan_file", f"{folder}/{path.name} is not in the manifest"))

    seen: set[str] = set()
    for image in library.images:
        if image.id in seen:
            issues.append(Issue("duplicate_hash", f"{image.id} appears twice", image.id))
        seen.add(image.id)

    with_images = enabled_tags(library)
    asked = {s.target_tag for s in library.playable_sounds("question") if s.target_tag}
    for tag in sorted(asked - with_images):
        issues.append(Issue("question_without_images", f"'{tag}' has a question but no pictures"))
    for tag in sorted(with_images - asked):
        issues.append(Issue("images_without_question", f"'{tag}' has pictures but no question"))

    playable = len(library.playable_images())
    if playable < option_count:
        issues.append(
            Issue(
                "not_enough_images",
                f"{playable} usable pictures, but a round needs {option_count}",
            )
        )
    return issues


# -- adding ----------------------------------------------------------------


def add_image(
    library: Library,
    src: Path,
    tags: list[str] | None = None,
    category: str | None = None,
    label: str | None = None,
    source: str = "file",
) -> Image:
    """Import `src` and attach parent-supplied tags.

    The same picture added twice has the same content hash, so its tags are merged
    into the existing entry instead of duplicating it (DATA_MODEL §4).
    """
    entry = import_image(src, library.root, source=source)
    entry.tags = normalise_tags(tags or [])
    entry.category = category
    entry.label = label

    existing = library.image_by_id(entry.id)
    if existing is not None:
        existing.tags = normalise_tags([*existing.tags, *entry.tags])
        existing.category = existing.category or category
        existing.label = existing.label or label
        return existing

    library.images.append(entry)
    return entry


def add_sound(
    library: Library,
    src: Path,
    kind: str,
    target_tag: str | None = None,
    label: str | None = None,
) -> Sound:
    """Adopt a WAV. A question needs exactly one target tag (SPEC §5)."""
    entry = adopt_audio(
        src,
        library.root,
        kind,
        target_tag=normalise_tag(target_tag) if target_tag else None,
        label=label,
    )
    existing = next((s for s in library.sounds if s.id == entry.id), None)
    if existing is not None:
        return existing
    library.sounds.append(entry)
    return entry
