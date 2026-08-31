"""Round selection rules (SPEC §2.1). Built in memory — no disk, no display."""

from pathlib import Path

from toddler_mouse_game.core.library import Library
from toddler_mouse_game.core.models import Image, Settings, Sound
from toddler_mouse_game.core.round_builder import RoundBuilder

ROUNDS = 200  # long enough that a rule broken once in a while still shows up


def img(image_id, tags=(), category=None, **kwargs):
    return Image(
        id=image_id,
        file=f"images/{image_id}.png",
        thumb=f"thumbs/{image_id}.jpg",
        tags=list(tags),
        category=category,
        **kwargs,
    )


def question(sound_id, tag):
    return Sound(
        id=sound_id, kind="question", file=f"audio/questions/{sound_id}.wav", target_tag=tag
    )


def library(images, sounds):
    return Library(root=Path("/nowhere"), images=list(images), sounds=list(sounds))


def basic(per_tag=2):
    """Six single-tag subjects across three categories — enough for n up to 6."""
    groups = {"animals": ("cat", "dog"), "things": ("car", "tree"), "sky": ("sun", "moon")}
    images, sounds = [], []
    for category, tags in groups.items():
        for tag in tags:
            for n in range(per_tag):
                images.append(img(f"{tag}{n}", [tag], category))
            sounds.append(question(f"q-{tag}", tag))
    return library(images, sounds)


def run(builder, count=ROUNDS):
    rounds = []
    for _ in range(count):
        built = builder.build()
        assert built is not None, f"ran dry after {len(rounds)} rounds"
        rounds.append(built)
    return rounds


# -- the two rules that stop her learning the wrong thing -------------------


def test_correct_answer_never_lands_in_the_same_slot_twice_running():
    for n in range(2, 7):
        builder = RoundBuilder(basic(), Settings(option_count=n), seed=n)
        indices = [r.correct_index for r in run(builder)]
        repeats = [i for i in range(1, len(indices)) if indices[i] == indices[i - 1]]
        assert not repeats, f"n={n}: slot repeated at rounds {repeats[:3]}"


def test_the_same_prompt_never_comes_twice_running():
    builder = RoundBuilder(basic(), Settings(option_count=3), seed=7)
    ids = [r.prompt.id for r in run(builder)]
    assert all(ids[i] != ids[i - 1] for i in range(1, len(ids)))


# -- distractors -----------------------------------------------------------


def test_no_distractor_shares_any_tag_with_the_correct_image():
    for n in range(2, 7):
        builder = RoundBuilder(basic(), Settings(option_count=n), seed=n)
        for built in run(builder, 60):
            correct_tags = set(built.correct.tags)
            for option in built.options:
                if option.id == built.correct.id:
                    continue
                assert built.prompt.target_tag not in option.tags
                assert not correct_tags & set(option.tags)


def test_a_shared_umbrella_tag_keeps_an_image_out_of_the_distractors():
    # "where is the animal?" must not offer a dog, because the dog is also an animal.
    images = [
        img("cat", ["cat", "animal"]),
        img("dog", ["dog", "animal"]),
        img("car", ["car"]),
        img("tree", ["tree"]),
    ]
    builder = RoundBuilder(
        library(images, [question("q", "animal")]), Settings(option_count=3), seed=1
    )
    for built in run(builder, 40):
        assert "dog" not in {o.id for o in built.options if o.id != built.correct.id}


def test_an_untagged_image_can_be_a_distractor_but_never_the_answer():
    images = [img("cat", ["cat"]), img("blank"), img("blank2")]
    builder = RoundBuilder(
        library(images, [question("q", "cat")]), Settings(option_count=2), seed=3
    )
    rounds = run(builder, 40)
    assert all(r.correct.id == "cat" for r in rounds)
    assert any("blank" in {o.id for o in r.options} for r in rounds)


# -- rotation and variety --------------------------------------------------


def test_every_recording_for_a_tag_gets_used():
    images = [img("cat0", ["cat"]), img("cat1", ["cat"]), img("x", ["other"]), img("y", ["other"])]
    sounds = [question(f"q{n}", "cat") for n in range(3)]
    builder = RoundBuilder(library(images, sounds), Settings(option_count=2), seed=5)
    assert {r.prompt.id for r in run(builder)} == {"q0", "q1", "q2"}


def test_several_pictures_for_one_tag_all_get_shown():
    # She should learn "cat" the concept, not one specific cat picture.
    images = [img(f"cat{n}", ["cat"]) for n in range(3)] + [img("x", ["other"])]
    builder = RoundBuilder(
        library(images, [question("q", "cat")]), Settings(option_count=2), seed=11
    )
    assert {r.correct.id for r in run(builder)} == {"cat0", "cat1", "cat2"}


# -- strategies ------------------------------------------------------------


def strategy_library():
    animals = [img(tag, [tag], "animals") for tag in ("cat", "dog", "bird", "fish", "horse")]
    vehicles = [img(tag, [tag], "vehicles") for tag in ("car", "bus", "train", "boat")]
    return library(animals + vehicles, [question("q-cat", "cat")])


def test_same_category_draws_distractors_from_the_correct_images_category():
    builder = RoundBuilder(
        strategy_library(), Settings(option_count=4, distractor_strategy="same_category"), seed=2
    )
    for built in run(builder, 40):
        assert all(o.category == "animals" for o in built.options)


def test_contrast_draws_distractors_from_other_categories():
    builder = RoundBuilder(
        strategy_library(), Settings(option_count=4, distractor_strategy="contrast"), seed=2
    )
    for built in run(builder, 40):
        others = [o for o in built.options if o.id != built.correct.id]
        assert all(o.category == "vehicles" for o in others)


def test_a_strategy_falls_back_rather_than_ending_the_session():
    # Only two other animals exist, so n=5 cannot be filled from the category alone.
    images = [img(tag, [tag], "animals") for tag in ("cat", "dog", "bird")]
    images += [img(tag, [tag], "vehicles") for tag in ("car", "bus")]
    builder = RoundBuilder(
        library(images, [question("q", "cat")]),
        Settings(option_count=5, distractor_strategy="same_category"),
        seed=4,
    )
    built = builder.build()
    assert built is not None and len(built.options) == 5


def test_mixed_is_free_to_cross_categories():
    builder = RoundBuilder(
        strategy_library(), Settings(option_count=4, distractor_strategy="mixed"), seed=2
    )
    seen = {o.category for built in run(builder, 60) for o in built.options}
    assert seen == {"animals", "vehicles"}


# -- shape of a round ------------------------------------------------------


def test_options_hold_the_correct_image_at_correct_index():
    for n in range(2, 7):
        builder = RoundBuilder(basic(), Settings(option_count=n), seed=n)
        for built in run(builder, 30):
            assert len(built.options) == n
            assert built.options[built.correct_index].id == built.correct.id
            assert len({o.id for o in built.options}) == n  # no picture twice in a round


def test_option_count_is_clamped_to_the_supported_range():
    assert RoundBuilder(basic(), Settings(option_count=0)).option_count == 2
    assert RoundBuilder(basic(), Settings(option_count=99)).option_count == 6


def test_the_same_seed_replays_the_same_session():
    first = [r.correct.id for r in run(RoundBuilder(basic(), Settings(), seed=42), 30)]
    second = [r.correct.id for r in run(RoundBuilder(basic(), Settings(), seed=42), 30)]
    assert first == second


# -- running out of content ------------------------------------------------


def test_empty_library_returns_none():
    assert RoundBuilder(library([], []), Settings()).build() is None


def test_no_question_for_any_tag_returns_none():
    images = [img("cat", ["cat"]), img("dog", ["dog"])]
    assert RoundBuilder(library(images, []), Settings()).build() is None


def test_a_question_whose_tag_has_no_pictures_is_skipped():
    images = [img("cat", ["cat"]), img("x", ["other"])]
    sounds = [question("q-truck", "truck"), question("q-cat", "cat")]
    builder = RoundBuilder(library(images, sounds), Settings(option_count=2), seed=1)
    assert all(r.prompt.id == "q-cat" for r in run(builder, 20))


def test_too_few_pictures_for_the_option_count_returns_none():
    images = [img("cat", ["cat"]), img("x", ["other"])]
    builder = RoundBuilder(library(images, [question("q", "cat")]), Settings(option_count=4))
    assert builder.build() is None


def test_disabled_and_broken_pictures_are_never_used():
    images = [
        img("cat", ["cat"]),
        img("x", ["other"]),
        img("off", ["other"], enabled=False),
        img("gone", ["other"], broken=True),
    ]
    builder = RoundBuilder(
        library(images, [question("q", "cat")]), Settings(option_count=2), seed=1
    )
    shown = {o.id for built in run(builder, 40) for o in built.options}
    assert shown == {"cat", "x"}


def test_enabled_categories_restricts_the_pool():
    builder = RoundBuilder(
        strategy_library(),
        Settings(option_count=3, enabled_categories=["animals"]),
        seed=6,
    )
    for built in run(builder, 40):
        assert all(o.category == "animals" for o in built.options)
