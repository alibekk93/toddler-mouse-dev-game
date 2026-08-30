"""Load and save `<library>/settings.json`. Pure Python — no Qt.

Two rules from DATA_MODEL §5: missing keys fall back to defaults, and unknown keys
are preserved on write, so a settings file from a newer version survives a round-trip
through an older build instead of being silently truncated.
"""

import json
import os
import types
from dataclasses import asdict, fields
from pathlib import Path
from typing import Union, get_args, get_origin, get_type_hints

from .models import Settings

SCHEMA_VERSION = 1
FILENAME = "settings.json"


def _matches(value: object, hint: object) -> bool:
    """Is `value` acceptable for a field annotated `hint`?

    A hand-edited `"option_count": "2"` must not reach the round builder, so a known
    key whose type is wrong falls back to its default. Range checking (n is 2-6, and
    so on) belongs with the settings page, not here.
    """
    if get_origin(hint) in (Union, types.UnionType):
        return any(_matches(value, arg) for arg in get_args(hint))
    origin = get_origin(hint) or hint  # list[str] -> list
    if origin is type(None):
        return value is None
    if isinstance(value, bool):
        return origin is bool  # bool is an int subclass; don't let it pass as one
    if origin is float:
        return isinstance(value, (int, float))  # JSON has no float/int distinction
    return isinstance(value, origin)


def load(library_dir: Path) -> Settings:
    """Read settings.json. A missing, unreadable, or corrupt file yields defaults."""
    try:
        raw = json.loads((Path(library_dir) / FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()

    hints = get_type_hints(Settings)
    known = {f.name for f in fields(Settings)} - {"extra"}
    values = {k: v for k, v in raw.items() if k in known and _matches(v, hints[k])}
    extra = {k: v for k, v in raw.items() if k not in known and k != "schema_version"}
    return Settings(**values, extra=extra)


def save(library_dir: Path, settings: Settings) -> None:
    """Write settings.json atomically, carrying any unknown keys back out."""
    data = asdict(settings)
    extra = data.pop("extra")
    payload = {"schema_version": SCHEMA_VERSION, **data, **extra}

    path = Path(library_dir) / FILENAME
    tmp = path.with_name(FILENAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
