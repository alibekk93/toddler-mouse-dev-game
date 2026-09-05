"""Normalise media on the way into the library. Pure Python — no Qt.

Both media types go through the full DATA_MODEL §8 pipeline: images are re-encoded and
thumbnailed, audio is folded to mono 16-bit, silence-trimmed, and peak-normalised. Both
return bytes rather than writing, so the caller hashes the *normalised* content for the id.

Imported images arrive **untagged**: the parent types tags in the staging tray
(SPEC §4.2), so tagging is the caller's job, never inferred from a filename.
"""

import hashlib
import sys
import wave
from array import array
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

FULL_SCALE = 32768  # 16-bit PCM
MAX_AUDIO_MS = 10_000  # a question longer than this is a different problem
TRIM_PAD_MS = 80
TRIM_FLOOR = round(FULL_SCALE * 10 ** (-45 / 20))  # -45 dBFS, amplitude 184
TARGET_PEAK = round(FULL_SCALE * 10 ** (-3 / 20))  # -3 dBFS, amplitude 23197

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


def to_int16(frames: bytes, width: int, channels: int = 1) -> array:
    """Convert raw little-endian PCM frames to int16, averaging down to one channel.

    `channels=1` leaves interleaving alone and only converts the sample width, which is
    what `audio/recorder.py` wants for the frames arriving off the microphone.
    """
    if width == 2:
        samples = array("h")
        samples.frombytes(frames[: len(frames) - len(frames) % 2])
        if sys.byteorder == "big":
            samples.byteswap()  # WAV is little-endian; array() is native
    elif width == 1:  # 8-bit WAV is unsigned, centred on 128
        samples = array("h", ((byte - 128) << 8 for byte in frames))
    else:  # 24- or 32-bit, keeping the top 16 bits
        shift = 8 * (width - 2)
        samples = array(
            "h",
            (
                int.from_bytes(frames[i : i + width], "little", signed=True) >> shift
                for i in range(0, len(frames) - width + 1, width)
            ),
        )

    if channels > 1:
        usable = len(samples) - len(samples) % channels
        samples = array(
            "h",
            (sum(samples[i : i + channels]) // channels for i in range(0, usable, channels)),
        )
    return samples


def _trim_silence(samples: array, rate: int) -> array:
    """Drop leading and trailing silence, leaving `TRIM_PAD_MS` of room each side.

    A clip that never crosses the floor is returned whole rather than emptied: a quiet
    recording is still a recording, and peak normalisation will bring it up.
    """
    loud = [i for i, value in enumerate(samples) if abs(value) >= TRIM_FLOOR]
    if not loud:
        return samples
    pad = round(rate * TRIM_PAD_MS / 1000)
    return samples[max(0, loud[0] - pad) : loud[-1] + 1 + pad]


def _peak_normalise(samples: array) -> array:
    """Bring the loudest sample to -3 dBFS so no question is much louder than another."""
    peak = max((abs(value) for value in samples), default=0)
    if not peak:
        return samples
    gain = TARGET_PEAK / peak
    return array(
        "h", (max(-FULL_SCALE, min(FULL_SCALE - 1, round(value * gain))) for value in samples)
    )


def normalise_audio(src: Path) -> tuple[bytes, int]:
    """Run DATA_MODEL §8's audio pipeline and return (wav_bytes, duration_ms).

    Nothing is written to disk here, so the caller can hash the normalised bytes and only
    then decide where they go — the same shape as `normalise_image`.
    """
    src = Path(src)
    try:
        with wave.open(str(src), "rb") as handle:
            if handle.getcomptype() != "NONE":
                raise ImportRejected(f"{src.name} is compressed; only plain PCM WAV is read")
            width, channels, rate = (
                handle.getsampwidth(),
                handle.getnchannels(),
                handle.getframerate(),
            )
            frames = handle.readframes(handle.getnframes())
    except ImportRejected:
        raise
    except (OSError, wave.Error, EOFError) as exc:
        raise ImportRejected(f"{src.name} is not a readable WAV") from exc
    if not rate or not channels or not 1 <= width <= 4:
        raise ImportRejected(f"{src.name} has an unusable WAV header")

    # ponytail: the source sample rate is kept, not resampled to 48k. QSoundEffect plays
    # any standard rate, and the recorder always produces 48k, so only imported files
    # differ. Add a resampler if a mixed-rate library ever sounds wrong.
    samples = _peak_normalise(_trim_silence(to_int16(frames, width, channels), rate))
    duration_ms = round(1000 * len(samples) / rate)
    if duration_ms > MAX_AUDIO_MS:
        raise ImportRejected(
            f"{src.name} is {duration_ms / 1000:.1f}s long; the limit is "
            f"{MAX_AUDIO_MS // 1000}s. Record a shorter one."
        )

    payload = samples
    if sys.byteorder == "big":
        payload = array("h", samples)
        payload.byteswap()

    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(payload.tobytes())
    return buffer.getvalue(), duration_ms


def adopt_audio(
    src: Path,
    library_root: Path,
    kind: str,
    target_tag: str | None = None,
    label: str | None = None,
) -> Sound:
    """Normalise a WAV into the library and return its manifest entry.

    Trim and peak normalisation happen here rather than at playback so the parent hears
    the finished clip in the record dialog, before deciding to keep it.
    """
    if kind not in AUDIO_DIRS:
        raise ImportRejected(f"unknown sound kind {kind!r}")
    if kind == "question" and not target_tag:
        raise ImportRejected("a question recording needs a target tag")

    data, duration_ms = normalise_audio(src)

    folder = Path(library_root) / AUDIO_DIRS[kind]
    folder.mkdir(parents=True, exist_ok=True)
    sound_id, duplicate = _allocate_id(hashlib.sha256(data).hexdigest(), folder, data)
    if not duplicate:
        (folder / f"{sound_id}.wav").write_bytes(data)

    return Sound(
        id=sound_id,
        kind=kind,
        file=f"{AUDIO_DIRS[kind]}/{sound_id}.wav",
        target_tag=target_tag,
        label=label,
        duration_ms=duration_ms,
        added_at=utc_now(),
    )
