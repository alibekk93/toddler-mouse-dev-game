"""Build a test library from the command line, so one exists before any UI does.

    python -m toddler_mouse_game.tools.seed --library ./testlib --images ./pics --tags cat,animal
    python -m toddler_mouse_game.tools.seed --library ./testlib --questions ./q --target-tag cat
    python -m toddler_mouse_game.tools.seed --library ./testlib --demo

Tags are supplied on the command line — this is the CLI form of the staging tray's tag
field (SPEC §4.2), including its bulk-tagging. Filenames are never parsed for tags:
files on disk are hash-named, and what a picture is called has nothing to do with what
it is of.
"""

import argparse
import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw

from ..core import library as library_mod
from ..core.importer import ImportRejected
from ..core.models import normalise_tags

IMAGE_SUFFIXES = library_mod.IMAGE_SUFFIXES

DEMO_COLOURS = {
    "red": (214, 74, 61),
    "blue": (61, 111, 217),
    "green": (76, 175, 80),
    "yellow": (242, 193, 78),
}
DEMO_SHAPES = ("circle", "square", "triangle", "star")
DEMO_GREY = (110, 110, 118)
DEMO_TONES = {  # one recognisable pitch per tag, so a human can tell them apart
    "red": 392.0,
    "blue": 440.0,
    "green": 494.0,
    "yellow": 523.0,
    "circle": 587.0,
    "square": 659.0,
    "triangle": 698.0,
    "star": 784.0,
}


# -- demo content ----------------------------------------------------------


def _draw(path: Path, shape: str, colour: tuple[int, int, int], size: int = 640) -> None:
    image = PILImage.new("RGB", (size, size), (245, 241, 232))
    draw = ImageDraw.Draw(image)
    pad = size // 8
    box = (pad, pad, size - pad, size - pad)
    if shape == "circle":
        draw.ellipse(box, fill=colour)
    elif shape == "square":
        draw.rectangle(box, fill=colour)
    elif shape == "triangle":
        draw.polygon([(size // 2, pad), (size - pad, size - pad), (pad, size - pad)], fill=colour)
    else:  # star
        points = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            radius = (size / 2 - pad) * (1.0 if i % 2 == 0 else 0.45)
            points.append(
                (size / 2 + radius * math.cos(angle), size / 2 - radius * math.sin(angle))
            )
        draw.polygon(points, fill=colour)
    image.save(path)


def _tone(path: Path, frequency: float, ms: int = 700, rate: int = 48_000) -> None:
    """A short sine with fades — a placeholder for a parent's voice, not a substitute."""
    total = int(rate * ms / 1000)
    fade = int(rate * 0.03)
    frames = bytearray()
    for n in range(total):
        envelope = min(1.0, n / fade, (total - n) / fade)
        value = int(20_000 * envelope * math.sin(2 * math.pi * frequency * n / rate))
        frames += struct.pack("<h", value)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


def _seed_demo(library, scratch: Path) -> None:
    """A working library from nothing: 16 pictures, 8 tags, 12 recordings."""
    scratch.mkdir(parents=True, exist_ok=True)

    # Two pictures per tag, so "prefer one not shown recently" has something to choose.
    for name, rgb in DEMO_COLOURS.items():
        for index, shape in enumerate(("circle", "square")):
            path = scratch / f"colour-{name}-{index}.png"
            _draw(path, shape, rgb)
            library_mod.add_image(library, path, tags=[name], categories=["colours"])

    for name in DEMO_SHAPES:
        for index, shade in enumerate((DEMO_GREY, (70, 70, 78))):
            path = scratch / f"shape-{name}-{index}.png"
            _draw(path, name, shade)
            library_mod.add_image(library, path, tags=[name], categories=["shapes"])

    for tag, frequency in DEMO_TONES.items():
        path = scratch / f"q-{tag}.wav"
        _tone(path, frequency)
        library_mod.add_sound(library, path, "question", target_tag=tag, label=f"where is {tag}?")

    # A second phrasing for two tags, so prompt rotation has something to rotate.
    for tag in ("red", "circle"):
        path = scratch / f"q-{tag}-2.wav"
        _tone(path, DEMO_TONES[tag] * 1.5)
        library_mod.add_sound(library, path, "question", target_tag=tag, label=f"find the {tag}")

    for index, frequency in enumerate((880.0, 988.0)):
        path = scratch / f"praise-{index}.wav"
        _tone(path, frequency, ms=500)
        library_mod.add_sound(library, path, "praise", label="well done")
    for index, frequency in enumerate((330.0, 294.0)):
        path = scratch / f"retry-{index}.wav"
        _tone(path, frequency, ms=500)
        library_mod.add_sound(library, path, "retry", label="try again")


# -- folder import ---------------------------------------------------------


def _files(folder: Path, suffixes: set[str] | None = None) -> list[Path]:
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and (suffixes is None or p.suffix.lower() in suffixes)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m toddler_mouse_game.tools.seed",
        description="Build a test library. Tags are given here, never read from filenames.",
    )
    # Required and never defaulted: this writes content, and content never belongs
    # inside the repo except under the gitignored testlib/ (CLAUDE.md rule 7).
    parser.add_argument("--library", type=Path, required=True, help="library folder to write into")
    parser.add_argument("--images", type=Path, help="folder of pictures to import")
    parser.add_argument("--tags", default="", help="comma-separated tags for every --images file")
    parser.add_argument(
        "--categories", default="", help="comma-separated categories for every --images file"
    )
    parser.add_argument("--questions", type=Path, help="folder of question WAVs")
    parser.add_argument("--target-tag", help="the tag every --questions file asks for")
    parser.add_argument("--praise", type=Path, help="folder of praise WAVs")
    parser.add_argument("--retry", type=Path, help="folder of retry WAVs")
    parser.add_argument("--demo", action="store_true", help="generate a whole library from nothing")
    args = parser.parse_args(argv)

    if args.questions and not args.target_tag:
        parser.error("--questions needs --target-tag (a question asks for exactly one tag)")
    if not any((args.images, args.questions, args.praise, args.retry, args.demo)):
        parser.error("nothing to do: pass --images, --questions, --praise, --retry, or --demo")

    root = Path(args.library)
    root.mkdir(parents=True, exist_ok=True)
    library, issues = library_mod.load(root)
    for issue in issues:
        print(f"  note: {issue.message}")

    # Count entries, not calls: re-importing the same picture merges into the existing
    # entry, so "added" must reflect what actually joined the library.
    before = len(library.images) + len(library.sounds)
    if args.demo:
        # Generate into a temp dir: the library folder holds only the layout that
        # DATA_MODEL §2 describes, since M5's export zips the whole thing.
        with tempfile.TemporaryDirectory(prefix="buska-seed-") as scratch:
            _seed_demo(library, Path(scratch))

    if args.images:
        tags = normalise_tags(args.tags.split(","))
        categories = normalise_tags(args.categories.split(","))
        for path in _files(args.images, IMAGE_SUFFIXES):
            try:
                library_mod.add_image(library, path, tags=tags, categories=categories)
            except ImportRejected as exc:
                print(f"  skipped {path.name}: {exc}")

    for folder, kind, target in (
        (args.questions, "question", args.target_tag),
        (args.praise, "praise", None),
        (args.retry, "retry", None),
    ):
        if not folder:
            continue
        for path in _files(folder, {".wav"}):
            try:
                library_mod.add_sound(library, path, kind, target_tag=target)
            except ImportRejected as exc:
                print(f"  skipped {path.name}: {exc}")

    library_mod.save(library)
    warnings = library_mod.validate(library)
    added = len(library.images) + len(library.sounds) - before
    print(f"{added} added -> {len(library.images)} images, {len(library.sounds)} sounds in {root}")
    for issue in warnings:
        print(f"  warning: {issue.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
