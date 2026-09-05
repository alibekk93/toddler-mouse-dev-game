"""Image and audio normalisation (DATA_MODEL §8). No display needed."""

import hashlib
import wave
from array import array
from io import BytesIO

import pytest
from conftest import make_image, make_wav
from PIL import Image as PILImage

from toddler_mouse_game.core import importer
from toddler_mouse_game.core.importer import (
    ImportRejected,
    adopt_audio,
    import_image,
    normalise_audio,
)


def read_samples(data: bytes) -> tuple[array, int, int, int]:
    """Unpack normalised WAV bytes into (samples, rate, channels, sampwidth)."""
    with wave.open(BytesIO(data), "rb") as handle:
        samples = array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
        return samples, handle.getframerate(), handle.getnchannels(), handle.getsampwidth()


# -- EXIF ------------------------------------------------------------------


def test_exif_orientation_is_applied(tmp_path):
    exif = PILImage.Exif()
    exif[0x0112] = 6  # rotate 90°: a 400x300 source becomes 300x400
    src = make_image(tmp_path / "rotated.jpg", size=(400, 300), exif=exif)

    entry = import_image(src, tmp_path / "lib")
    assert (entry.width, entry.height) == (300, 400)


def test_exif_is_stripped(tmp_path):
    exif = PILImage.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "SomePhoneMaker"  # stand-in for the GPS tags a real photo carries
    src = make_image(tmp_path / "tagged.jpg", exif=exif)

    entry = import_image(src, tmp_path / "lib")
    with PILImage.open(tmp_path / "lib" / entry.file) as written:
        assert dict(written.getexif()) == {}


# -- size ------------------------------------------------------------------


def test_long_edge_is_clamped(tmp_path):
    src = make_image(tmp_path / "huge.jpg", size=(3000, 1500))
    entry = import_image(src, tmp_path / "lib")
    assert max(entry.width, entry.height) == importer.MAX_EDGE
    assert (entry.width, entry.height) == (1600, 800)


def test_small_images_are_not_enlarged(tmp_path):
    src = make_image(tmp_path / "small.jpg", size=(120, 90))
    entry = import_image(src, tmp_path / "lib")
    assert (entry.width, entry.height) == (120, 90)


def test_thumbnail_is_written_and_bounded(tmp_path):
    src = make_image(tmp_path / "pic.jpg", size=(1200, 900))
    entry = import_image(src, tmp_path / "lib")
    with PILImage.open(tmp_path / "lib" / entry.thumb) as thumb:
        assert max(thumb.size) == importer.THUMB_EDGE


# -- rejection -------------------------------------------------------------


def test_oversized_file_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_SOURCE_BYTES", 128)
    src = make_image(tmp_path / "big.jpg", size=(800, 800))
    with pytest.raises(ImportRejected, match="over"):
        import_image(src, tmp_path / "lib")


def test_pathological_dimensions_are_rejected_before_decoding(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "MAX_SOURCE_PIXELS", 1000)
    src = make_image(tmp_path / "bomb.png", size=(400, 300))
    with pytest.raises(ImportRejected, match="pathological"):
        import_image(src, tmp_path / "lib")


def test_malformed_image_does_not_crash_the_caller(tmp_path):
    src = tmp_path / "not-really.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 20)
    with pytest.raises(ImportRejected, match="readable image"):
        import_image(src, tmp_path / "lib")


# -- encoding --------------------------------------------------------------


def test_transparent_source_becomes_png(tmp_path):
    src = make_image(tmp_path / "alpha.png", mode="RGBA", colour=(200, 60, 60, 0))
    entry = import_image(src, tmp_path / "lib")
    assert entry.file.endswith(".png")


def test_opaque_rgba_source_becomes_jpeg(tmp_path):
    # An alpha channel that is fully opaque is not "genuinely transparent".
    src = make_image(tmp_path / "opaque.png", mode="RGBA", colour=(200, 60, 60, 255))
    entry = import_image(src, tmp_path / "lib")
    assert entry.file.endswith(".jpg")


def test_gif_is_flattened_to_first_frame(tmp_path):
    first = PILImage.new("RGB", (200, 200), (255, 0, 0))
    second = PILImage.new("RGB", (200, 200), (0, 0, 255))
    src = tmp_path / "animated.gif"
    first.save(src, save_all=True, append_images=[second])

    entry = import_image(src, tmp_path / "lib")
    with PILImage.open(tmp_path / "lib" / entry.file) as written:
        assert written.convert("RGB").getpixel((100, 100))[0] > 200  # the red frame


# -- ids -------------------------------------------------------------------


def test_same_picture_twice_yields_the_same_id(tmp_path):
    src = make_image(tmp_path / "cat.jpg")
    first = import_image(src, tmp_path / "lib")
    second = import_image(src, tmp_path / "lib")
    assert first.id == second.id
    assert len(list((tmp_path / "lib" / "images").iterdir())) == 1


def test_different_content_sharing_a_prefix_extends_the_id(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    digest = "abcdef01" + "2345" + "f" * 52
    (folder / "abcdef01.png").write_bytes(b"someone else's bytes")

    allocated, duplicate = importer._allocate_id(digest, folder, b"my bytes")
    assert allocated == "abcdef012345"
    assert duplicate is False


# -- audio -----------------------------------------------------------------


def test_adopted_audio_reports_duration(tmp_path):
    src = make_wav(tmp_path / "q.wav", ms=750)
    entry = adopt_audio(src, tmp_path / "lib", "question", target_tag="cat")
    assert entry.duration_ms == 750
    assert entry.file.startswith("audio/questions/")
    assert (tmp_path / "lib" / entry.file).is_file()


def test_praise_and_retry_land_in_their_own_folders(tmp_path):
    praise = adopt_audio(make_wav(tmp_path / "p.wav"), tmp_path / "lib", "praise")
    retry = adopt_audio(make_wav(tmp_path / "r.wav", frequency=300.0), tmp_path / "lib", "retry")
    assert praise.file.startswith("audio/praise/")
    assert retry.file.startswith("audio/retry/")
    assert praise.target_tag is None


def test_question_without_a_target_tag_is_rejected(tmp_path):
    src = make_wav(tmp_path / "q.wav")
    with pytest.raises(ImportRejected, match="target tag"):
        adopt_audio(src, tmp_path / "lib", "question")


def test_non_wav_is_rejected(tmp_path):
    src = tmp_path / "song.wav"
    src.write_bytes(b"this is not a wav file")
    with pytest.raises(ImportRejected, match="readable WAV"):
        adopt_audio(src, tmp_path / "lib", "praise")


# -- audio normalisation (DATA_MODEL §8) -----------------------------------


def test_silence_is_trimmed_leaving_padding(tmp_path):
    src = make_wav(tmp_path / "q.wav", ms=400, silence_ms=300)
    data, duration_ms = normalise_audio(src)

    # 300ms of silence each side collapses to the 80ms of padding each side.
    assert duration_ms == pytest.approx(400 + 2 * importer.TRIM_PAD_MS, abs=5)
    samples, *_ = read_samples(data)
    assert len(samples) == pytest.approx(duration_ms * 48, abs=250)


def test_a_quiet_recording_is_brought_up_to_target(tmp_path):
    src = make_wav(tmp_path / "quiet.wav", amplitude=1_500)
    samples, *_ = read_samples(normalise_audio(src)[0])
    assert max(abs(s) for s in samples) == pytest.approx(importer.TARGET_PEAK, abs=2)


def test_a_loud_recording_is_brought_down_and_never_clips(tmp_path):
    src = make_wav(tmp_path / "loud.wav", amplitude=32_000)
    samples, *_ = read_samples(normalise_audio(src)[0])
    assert max(abs(s) for s in samples) == pytest.approx(importer.TARGET_PEAK, abs=2)
    assert all(-32768 <= s <= 32767 for s in samples)


def test_stereo_24bit_becomes_mono_16bit_at_the_source_rate(tmp_path):
    # 44.1kHz is kept, not resampled — see the ponytail note in normalise_audio.
    src = make_wav(tmp_path / "stereo.wav", rate=44_100, channels=2, width=3)
    samples, rate, channels, width = read_samples(normalise_audio(src)[0])
    assert (rate, channels, width) == (44_100, 1, 2)
    assert max(abs(s) for s in samples) == pytest.approx(importer.TARGET_PEAK, abs=2)


def test_eight_bit_source_is_accepted(tmp_path):
    src = make_wav(tmp_path / "old.wav", width=1)
    samples, _, channels, width = read_samples(normalise_audio(src)[0])
    assert (channels, width) == (1, 2)
    assert max(abs(s) for s in samples) > 0


def test_a_recording_over_the_cap_is_rejected_not_truncated(tmp_path):
    src = make_wav(tmp_path / "long.wav", ms=importer.MAX_AUDIO_MS + 500)
    with pytest.raises(ImportRejected, match="the limit is 10s"):
        normalise_audio(src)


def test_silent_input_stays_a_valid_wav(tmp_path):
    src = make_wav(tmp_path / "silent.wav", ms=300, amplitude=0)
    data, duration_ms = normalise_audio(src)
    samples, *_ = read_samples(data)
    assert duration_ms == 300  # nothing crosses the floor, so nothing is trimmed away
    assert set(samples) == {0}


def test_the_id_is_the_hash_of_the_normalised_bytes(tmp_path):
    src = make_wav(tmp_path / "quiet.wav", amplitude=1_500, silence_ms=200)
    entry = adopt_audio(src, tmp_path / "lib", "praise")

    written = (tmp_path / "lib" / entry.file).read_bytes()
    assert written != src.read_bytes()  # normalised on the way in, not copied
    assert hashlib.sha256(written).hexdigest().startswith(entry.id)

    # And the same source adopted twice is still one file on disk.
    assert adopt_audio(src, tmp_path / "lib", "praise").id == entry.id
    assert len(list((tmp_path / "lib" / "audio" / "praise").iterdir())) == 1


def test_normalising_twice_is_idempotent(tmp_path):
    """The record dialog normalises on stop and `adopt_audio` normalises again on Keep."""
    src = make_wav(tmp_path / "take.wav", ms=400, silence_ms=200)
    once, _ = normalise_audio(src)
    (tmp_path / "once.wav").write_bytes(once)
    twice, _ = normalise_audio(tmp_path / "once.wav")
    assert once == twice
