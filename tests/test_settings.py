"""Settings round-tripping and tag normalisation. No display needed."""

import json
import unicodedata

from toddler_mouse_game.core import settings as settings_mod
from toddler_mouse_game.core.models import Settings, normalise_tag, normalise_tags


def read_json(library_dir):
    return json.loads((library_dir / "settings.json").read_text(encoding="utf-8"))


def write_json(library_dir, payload):
    (library_dir / "settings.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# -- defaults --------------------------------------------------------------


def test_missing_file_yields_defaults(tmp_path):
    assert settings_mod.load(tmp_path) == Settings()


def test_corrupt_file_yields_defaults_and_does_not_raise(tmp_path):
    (tmp_path / "settings.json").write_text("{not json at all", encoding="utf-8")
    assert settings_mod.load(tmp_path) == Settings()


def test_missing_keys_fall_back_to_defaults(tmp_path):
    write_json(tmp_path, {"option_count": 4})
    loaded = settings_mod.load(tmp_path)
    assert loaded.option_count == 4
    assert loaded.celebrate_duration == Settings().celebrate_duration


# -- forward compatibility -------------------------------------------------


def test_unknown_keys_survive_a_round_trip(tmp_path):
    write_json(tmp_path, {"option_count": 3, "invented_in_v9": {"nested": [1, 2]}})

    loaded = settings_mod.load(tmp_path)
    assert loaded.extra == {"invented_in_v9": {"nested": [1, 2]}}

    settings_mod.save(tmp_path, loaded)
    written = read_json(tmp_path)
    assert written["invented_in_v9"] == {"nested": [1, 2]}
    assert written["option_count"] == 3
    assert written["schema_version"] == settings_mod.SCHEMA_VERSION
    assert "extra" not in written


def test_save_then_load_is_stable(tmp_path):
    original = Settings(option_count=5, cursor_scale=1.4, hint_after=None)
    settings_mod.save(tmp_path, original)
    assert settings_mod.load(tmp_path) == original


# -- type gate -------------------------------------------------------------


def test_wrong_type_falls_back_to_default(tmp_path):
    write_json(tmp_path, {"option_count": "4", "repeat_question": "yes"})
    loaded = settings_mod.load(tmp_path)
    assert loaded.option_count == Settings().option_count
    assert loaded.repeat_question is Settings().repeat_question


def test_bool_does_not_pass_as_int(tmp_path):
    write_json(tmp_path, {"option_count": True})
    assert settings_mod.load(tmp_path).option_count == Settings().option_count


def test_int_is_accepted_for_a_float_field(tmp_path):
    write_json(tmp_path, {"repeat_interval": 12})  # JSON has no float/int distinction
    assert settings_mod.load(tmp_path).repeat_interval == 12


def test_nullable_fields_accept_both(tmp_path):
    write_json(tmp_path, {"hint_after": None, "enabled_categories": ["animals"]})
    loaded = settings_mod.load(tmp_path)
    assert loaded.hint_after is None
    assert loaded.enabled_categories == ["animals"]


# -- tags: opaque strings in any script ------------------------------------


def test_casefold_not_lower_on_cyrillic():
    assert normalise_tag("  Кошка  ") == "кошка"


def test_casefold_handles_sharp_s():
    assert normalise_tag("STRASSE") == normalise_tag("Straße")


def test_decomposed_accents_normalise_to_nfc():
    decomposed = unicodedata.normalize("NFD", "Café")
    assert decomposed != "café"
    assert normalise_tag(decomposed) == "café"
    assert normalise_tag(decomposed) == normalise_tag("CAFÉ")


def test_tags_dedupe_and_keep_order():
    assert normalise_tags(["Cat", " cat ", "", "animal"]) == ["cat", "animal"]


def test_manifest_stays_readable_to_a_human(tmp_path):
    settings_mod.save(tmp_path, Settings(enabled_categories=["кошки"]))
    raw = (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert "кошки" in raw  # ensure_ascii=False, not ко...
