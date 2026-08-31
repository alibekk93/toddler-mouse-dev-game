"""Normalise media on the way into the library. Pure Python — no Qt.

Images go through the full DATA_MODEL §8 pipeline. Audio is only *adopted* here —
copied and measured — because the trim and loudness normalisation belong with the
recorder at M3, which is the only place they can be judged by ear.

Imported images arrive **untagged**: the parent types tags in the staging tray
(SPEC §4.2), so tagging is the caller's job, never inferred from a filename.
"""

import hashlib
import shutil
import wave
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageOps

from .models import Image, Sound, utc_now

MAX_SOURCE_BYTES = 50 * 1024 * 1024  # DATA_MODEL §8.6
MAX_SOURCE_PIXELS = 80_000_000  # a "pathological dimensions" guard, checked pre-decode
MAX_SOURCE_EDGE = 20_000
MAX_EDGE = 1600  # nobody needs 4000px of cat on a 1080p screen
THUMB_EDGE = 256
JPEG_QUALITY = 88

AUDIO_DIRS = {  # note: "questions" is plural, the other two are not (DATA_MODEL §2)
    "question": "audio/questions",
    "praise": "audio/praise",
    "retry": "audio/retry",
}


class ImportRejected(ValueError):
    """The source file cannot be imported. Carries a message fit to show a parent."""


# -- ids -------------------------------------------------------------------


def _allocate_id(digest: str, folder: Path, data: bytes) -> tuple[str, bool]:
    """Return (id, is_duplicate) for content `data` whose sha256 hex is `digest`.

    An 8-hex prefix gives free duplicate detection (DATA_MODEL §3): the same picture
    imported twice normalises to the same bytes, so it lands on the same id. A genuine
    prefix collision between *different* content extends the id instead of clobbering.
    """
    for length in (8, 12, len(digest)):
        candidate = digest[:length]
        existing = sorted(folder.glob(candidate + ".*"))
        if not existing:
            return candidate, False
        if any(path.read_bytes() == data for path in existing):
            return candidate, True
    raise ImportRejected("could not allocate an id for this file")


# -- images ----------------------------------------------------------------


def _is_transparent(img: PILImage.Image) -> bool:
    if img.mode in ("RGBA", "LA"):
        return img.getchannel("A").getextrema()[0] < 255
    return False


def normalise_image(src: Path) -> tuple[bytes, bytes, str, int, int]:
    """Run DATA_MODEL §8 and return (image_bytes, thumb_bytes, extension, w, h).

    Nothing is written to disk here, which is what lets the caller hash the normalised
    bytes and only then decide where they go.
    """
    src = Path(src)
    try:
        size_bytes = src.stat().st_size
    except OSError as exc:
        raise ImportRejected(f"cannot read {src.name}") from exc
    if size_bytes > MAX_SOURCE_BYTES:
        raise ImportRejected(f"{src.name} is over {MAX_SOURCE_BYTES // 1024 // 1024}MB")

    try:
        with PILImage.open(src) as probe:
            # open() only reads the header, so this rejects a decompression bomb
            # before any pixels are decoded.
            width, height = probe.size
            if width * height > MAX_SOURCE_PIXELS or max(width, height) > MAX_SOURCE_EDGE:
                raise ImportRejected(f"{src.name} has pathological dimensions ({width}x{height})")

            img = ImageOps.exif_transpose(probe)  # apply orientation...
            img.load()  # ...GIFs stay on frame 1: nothing seeks past it
    except ImportRejected:
        raise
    except Exception as exc:  # a malformed image must not take down the caller
        raise ImportRejected(f"{src.name} is not a readable image") from exc

    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    transparent = _is_transparent(img)
    img = img.convert("RGBA" if transparent else "RGB")

    img.thumbnail((MAX_EDGE, MAX_EDGE), PILImage.LANCZOS)  # thumbnail() never enlarges

    buffer = BytesIO()
    if transparent:
        img.save(buffer, "PNG", optimize=True)  # no exif= argument: EXIF is dropped here
        extension = "png"
    else:
        img.save(buffer, "JPEG", quality=JPEG_QUALITY)
        extension = "jpg"

    thumb = img.convert("RGB")
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), PILImage.LANCZOS)
    thumb_buffer = BytesIO()
    thumb.save(thumb_buffer, "JPEG", quality=JPEG_QUALITY)

    return buffer.getvalue(), thumb_buffer.getvalue(), extension, img.width, img.height


def import_image(src: Path, library_root: Path, source: str = "file") -> Image:
    """Normalise `src` into the library and return an untagged `Image` entry."""
    data, thumb_data, extension, width, height = normalise_image(src)

    root = Path(library_root)
    images_dir = root / "images"
    thumbs_dir = root / "thumbs"
    images_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    image_id, duplicate = _allocate_id(hashlib.sha256(data).hexdigest(), images_dir, data)
    if not duplicate:
        (images_dir / f"{image_id}.{extension}").write_bytes(data)
        (thumbs_dir / f"{image_id}.jpg").write_bytes(thumb_data)

    return Image(
        id=image_id,
        file=f"images/{image_id}.{extension}",
        thumb=f"thumbs/{image_id}.jpg",
        source=source,
        added_at=utc_now(),
        width=width,
        height=height,
    )


# -- audio -----------------------------------------------------------------


def adopt_audio(
    src: Path,
    library_root: Path,
    kind: str,
    target_tag: str | None = None,
    label: str | None = None,
) -> Sound:
    """Copy a WAV into the library as-is and measure it.

    No trim, no peak normalisation — those arrive at M3 with the recorder
    (DATA_MODEL §8), where a person can hear whether the trim ate a soft first word.
    """
    if kind not in AUDIO_DIRS:
        raise ImportRejected(f"unknown sound kind {kind!r}")
    if kind == "question" and not target_tag:
        raise ImportRejected("a question recording needs a target tag")

    src = Path(src)
    try:
        data = src.read_bytes()
        with wave.open(str(src), "rb") as handle:
            frames, rate = handle.getnframes(), handle.getframerate()
    except (OSError, wave.Error) as exc:
        raise ImportRejected(f"{src.name} is not a readable WAV") from exc
    if not rate:
        raise ImportRejected(f"{src.name} has no sample rate")

    folder = Path(library_root) / AUDIO_DIRS[kind]
    folder.mkdir(parents=True, exist_ok=True)
    sound_id, duplicate = _allocate_id(hashlib.sha256(data).hexdigest(), folder, data)
    destination = folder / f"{sound_id}.wav"
    if not duplicate:
        shutil.copyfile(src, destination)

    return Sound(
        id=sound_id,
        kind=kind,
        file=f"{AUDIO_DIRS[kind]}/{sound_id}.wav",
        target_tag=target_tag,
        label=label,
        duration_ms=round(1000 * frames / rate),
        added_at=utc_now(),
    )
