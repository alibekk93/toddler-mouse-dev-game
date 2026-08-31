"""Content and settings models. Pure Python — no Qt below this line."""

import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> str:
    """Manifest timestamp format, e.g. `2026-08-30T13:55:02Z` (DATA_MODEL §3)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise_tag(tag: str) -> str:
    """Strip, NFC-normalise, casefold.

    `casefold`, not `lower`: tags are opaque strings in any script (DATA_MODEL §3),
    and `lower` gets Cyrillic and German sharp-s wrong.
    """
    return unicodedata.normalize("NFC", tag.strip()).casefold()


def normalise_tags(tags: list[str]) -> list[str]:
    """Normalise and dedupe, preserving first-seen order."""
    return list(dict.fromkeys(normalise_tag(t) for t in tags if t.strip()))


@dataclass(slots=True)
class Image:
    """One picture in the library. Paths are relative to the library root, always."""

    id: str
    file: str
    thumb: str
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    label: str | None = None
    enabled: bool = True
    source: str = "file"  # clipboard | file | drop
    added_at: str = ""
    width: int = 0
    height: int = 0
    broken: bool = False  # file missing from disk; excluded from rounds


@dataclass(slots=True)
class Sound:
    """One recording. `target_tag` is required for kind="question", absent otherwise."""

    id: str
    kind: str  # question | praise | retry
    file: str
    target_tag: str | None = None
    label: str | None = None
    duration_ms: int = 0
    enabled: bool = True
    added_at: str = ""
    broken: bool = False


@dataclass(slots=True)
class Settings:
    """SPEC §4.4, plus `reduced_motion` (UX §7) and `cursor_mode` (ARCHITECTURE §4.1)."""

    option_count: int = 2  # 2-6
    distractor_strategy: str = "mixed"  # mixed | same_category | contrast
    enabled_categories: list[str] | None = None  # None = all
    repeat_question: bool = True
    repeat_interval: float = 8.0  # seconds, 4-30
    hint_after: int | None = 2  # repeat ticks before hinting; None = off
    celebrate_duration: float = 2.5  # seconds, 1-5
    cursor_style: str = "paw"
    cursor_scale: float = 1.0  # 0.6-2.0
    master_volume: float = 0.8
    confetti: bool = True
    warmup_shape_count: int = 6  # 4-8
    show_tag_caption: bool = False
    reduced_motion: bool = False
    cursor_mode: str = "sprite"  # sprite | hardware

    # Keys from a settings.json written by a newer version. Preserved on save,
    # never interpreted. See core/settings.py.
    extra: dict = field(default_factory=dict)
