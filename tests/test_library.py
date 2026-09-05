"""Manifest durability, repair, and the DATA_MODEL §4 validation table."""

import json

from conftest import make_image, make_wav

from toddler_mouse_game.core import library as lib
from toddler_mouse_game.core.models import Image, Sound


def codes(issues):
    return {issue.code for issue in issues}


def seeded(tmp_path, tags=("cat",), extra=1):
    """A library with one tagged picture, a question for it, and some plain distractors."""
    root = tmp_path / "lib"
    library = lib.Library(root=root)
    lib.add_image(library, make_image(tmp_path / "cat.jpg", colour=(10, 20, 30)), tags=list(tags))
    for n in range(extra):
        source = make_image(tmp_path / f"other{n}.jpg", colour=(n * 40 + 5, 90, 200))
        lib.add_image(library, source, tags=[f"thing{n}"])
    lib.add_sound(library, make_wav(tmp_path / "q.wav"), "question", target_tag=tags[0])
    return library


# -- the write protocol ----------------------------------------------------


def test_save_writes_a_manifest_and_leaves_no_tmp(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    assert (library.root / "library.json").is_file()
    assert not (library.root / "library.json.tmp").exists()


def test_second_save_rotates_the_previous_version_into_bak(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    first = json.loads((library.root / "library.json").read_text(encoding="utf-8"))

    library.images[0].tags = ["cat", "animal"]
    lib.save(library)

    backup = json.loads((library.root / "library.json.bak").read_text(encoding="utf-8"))
    live = json.loads((library.root / "library.json").read_text(encoding="utf-8"))
    assert backup["images"][0]["tags"] == first["images"][0]["tags"] == ["cat"]
    assert live["images"][0]["tags"] == ["cat", "animal"]


def test_manifest_holds_only_relative_paths(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    raw = (library.root / "library.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    for entry in json.loads(raw)["images"]:
        assert entry["file"].startswith("images/")


def test_broken_is_not_persisted(tmp_path):
    library = seeded(tmp_path)
    library.images[0].broken = True
    lib.save(library)
    entry = json.loads((library.root / "library.json").read_text(encoding="utf-8"))["images"][0]
    assert "broken" not in entry  # recomputed from disk on every validate()


# -- repair ----------------------------------------------------------------


def test_corrupt_manifest_is_restored_from_bak(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    lib.save(library)  # now a good .bak exists
    (library.root / "library.json").write_text("{ truncated", encoding="utf-8")

    reloaded, issues = lib.load(library.root)
    assert "restored_from_bak" in codes(issues)
    assert len(reloaded.images) == len(library.images)


def test_corrupt_manifest_and_bak_rebuilds_from_disk(tmp_path):
    library = seeded(tmp_path, extra=2)
    lib.save(library)
    (library.root / "library.json").write_text("{ truncated", encoding="utf-8")
    (library.root / "library.json.bak").write_text("also ruined", encoding="utf-8")

    reloaded, issues = lib.load(library.root)
    assert "rebuilt_from_disk" in codes(issues)
    # The pictures are still there; they have simply lost their tags.
    assert len(reloaded.images) == len(library.images)
    assert all(image.tags == [] for image in reloaded.images)
    assert len(reloaded.sounds) == 1


def test_corrupt_manifest_is_never_overwritten_on_load(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    (library.root / "library.json").write_text("{ truncated", encoding="utf-8")
    lib.load(library.root)
    assert (library.root / "library.json").read_text(encoding="utf-8") == "{ truncated"


def test_empty_folder_is_not_a_problem(tmp_path):
    library, issues = lib.load(tmp_path / "fresh")
    assert library.images == [] and library.sounds == []
    assert issues == []


def test_unknown_manifest_keys_do_not_break_loading(tmp_path):
    library = seeded(tmp_path)
    lib.save(library)
    path = library.root / "library.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["images"][0]["invented_in_v9"] = True
    path.write_text(json.dumps(data), encoding="utf-8")

    reloaded, _ = lib.load(library.root)
    assert len(reloaded.images) == len(library.images)


# -- validation ------------------------------------------------------------


def test_missing_file_is_marked_broken_and_drops_out_of_play(tmp_path):
    library = seeded(tmp_path)
    (library.root / library.images[0].file).unlink()

    issues = lib.validate(library)
    assert "missing_file" in codes(issues)
    assert library.images[0].broken is True
    assert library.images[0] not in library.playable_images()


def test_orphan_file_is_offered_for_adoption(tmp_path):
    library = seeded(tmp_path)
    (library.root / "images" / "stray.png").write_bytes(b"not in the manifest")
    assert "orphan_file" in codes(lib.validate(library))


def test_question_with_no_pictures_is_a_warning_not_an_error(tmp_path):
    library = seeded(tmp_path)
    lib.add_sound(
        library, make_wav(tmp_path / "q2.wav", frequency=300.0), "question", target_tag="truck"
    )
    issues = lib.validate(library)
    assert "question_without_images" in codes(issues)
    assert any("truck" in issue.message for issue in issues)


def test_pictures_with_no_question_is_a_warning(tmp_path):
    library = seeded(tmp_path, extra=1)
    assert "images_without_question" in codes(lib.validate(library))


def test_too_few_pictures_for_the_option_count(tmp_path):
    library = seeded(tmp_path, extra=0)
    assert "not_enough_images" in codes(lib.validate(library, option_count=4))
    assert "not_enough_images" not in codes(lib.validate(library, option_count=1))


def test_duplicate_id_in_a_hand_edited_manifest_is_reported(tmp_path):
    library = seeded(tmp_path)
    library.images.append(library.images[0])
    assert "duplicate_hash" in codes(lib.validate(library))


def test_validate_never_raises_on_a_wrecked_library(tmp_path):
    library = lib.Library(root=tmp_path / "gone")
    library.images.append(Image(id="x", file="images/x.png", thumb="thumbs/x.jpg", tags=["cat"]))
    library.sounds.append(Sound(id="y", kind="question", file="audio/questions/y.wav"))
    assert lib.validate(library)  # warnings, not an exception


# -- adding ----------------------------------------------------------------


def test_the_same_picture_added_twice_merges_tags(tmp_path):
    root = tmp_path / "lib"
    library = lib.Library(root=root)
    source = make_image(tmp_path / "cat.jpg")

    lib.add_image(library, source, tags=["cat"])
    lib.add_image(library, source, tags=["animal", "cat"])

    assert len(library.images) == 1
    assert library.images[0].tags == ["cat", "animal"]


def test_tags_are_normalised_on_the_way_in(tmp_path):
    root = tmp_path / "lib"
    library = lib.Library(root=root)
    lib.add_image(library, make_image(tmp_path / "cat.jpg"), tags=["  Кошка ", "CAT", "cat"])
    assert library.images[0].tags == ["кошка", "cat"]


def test_non_latin_tags_survive_a_round_trip_and_stay_readable(tmp_path):
    root = tmp_path / "lib"
    library = lib.Library(root=root)
    lib.add_image(library, make_image(tmp_path / "cat.jpg"), tags=["кошка"])
    lib.add_sound(library, make_wav(tmp_path / "q.wav"), "question", target_tag="Кошка")
    lib.save(library)

    raw = (root / "library.json").read_text(encoding="utf-8")
    assert "кошка" in raw  # ensure_ascii=False

    reloaded, _ = lib.load(root)
    assert reloaded.images[0].tags == ["кошка"]
    assert reloaded.sounds[0].target_tag == "кошка"
    assert lib.enabled_tags(reloaded) == {"кошка"}


def test_a_russian_question_matches_its_russian_pictures(tmp_path):
    library = lib.Library(root=tmp_path / "lib")
    lib.add_image(library, make_image(tmp_path / "cat.jpg"), tags=["кошка"])
    lib.add_sound(library, make_wav(tmp_path / "q.wav"), "question", target_tag="КОШКА")
    assert "question_without_images" not in codes(lib.validate(library))


# -- deletion and tag listing ----------------------------------------------


def test_deleting_an_image_moves_it_to_trash_and_never_unlinks(tmp_path):
    library = seeded(tmp_path)
    image = library.images[0]
    lib.remove_image(library, image)

    assert library.image_by_id(image.id) is None
    assert not (library.root / image.file).exists()
    assert (library.root / "_trash" / image.file).is_file()
    assert (library.root / "_trash" / image.thumb).is_file()


def test_deleting_a_recording_moves_it_to_trash(tmp_path):
    library = seeded(tmp_path)
    sound = library.sounds[0]
    lib.remove_sound(library, sound)

    assert library.sounds == []
    assert (library.root / "_trash" / sound.file).is_file()


def test_trashing_the_same_name_twice_keeps_both(tmp_path):
    """Delete, re-add, delete again: the second must not overwrite the first in the
    trash, which would be a deletion by another name."""
    library = seeded(tmp_path)
    source = make_image(tmp_path / "cat.jpg", colour=(10, 20, 30))
    first = library.images[0]
    lib.remove_image(library, first)
    lib.remove_image(library, lib.add_image(library, source, tags=["cat"]))

    trashed = sorted(p.name for p in (library.root / "_trash" / "images").iterdir())
    assert len(trashed) == 2


def test_all_tags_includes_disabled_pictures_and_unanswered_questions(tmp_path):
    library = seeded(tmp_path)
    library.images[0].enabled = False
    lib.add_sound(
        library, make_wav(tmp_path / "q2.wav", frequency=300.0), "question", target_tag="truck"
    )

    assert "cat" in lib.all_tags(library)  # disabled, but still a tag you can record for
    assert "truck" in lib.all_tags(library)  # asked for, no pictures yet
    assert lib.all_tags(library) == sorted(lib.all_tags(library))


def test_the_same_clip_can_be_both_a_question_and_a_praise_line(tmp_path):
    """Ids are unique within a kind, not across them — each kind has its own folder.
    Matching on id alone dropped the second entry and orphaned the file it had written."""
    library = lib.Library(root=tmp_path / "lib")
    source = make_wav(tmp_path / "yes.wav")
    question = lib.add_sound(library, source, "question", target_tag="cat")
    praise = lib.add_sound(library, source, "praise")

    assert question.id == praise.id  # same audio, so the same content hash
    assert [s.kind for s in library.sounds] == ["question", "praise"]
    assert "orphan_file" not in codes(lib.validate(library))
