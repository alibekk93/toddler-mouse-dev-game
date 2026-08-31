"""Image normalisation and audio adoption (DATA_MODEL §8). No display needed."""

import pytest
from conftest import make_image, make_wav
from PIL import Image as PILImage

from toddler_mouse_game.core import importer
from toddler_mouse_game.core.importer import ImportRejected, adopt_audio, import_image

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
