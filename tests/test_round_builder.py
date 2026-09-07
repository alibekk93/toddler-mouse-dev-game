"""Round selection rules (SPEC §2.1). Built in memory — no disk, no display."""

from pathlib import Path

from toddler_mouse_game.core.library import Library
from toddler_mouse_game.core.models import Image, Settings, Sound
from toddler_mouse_game.core.round_builder import RoundBuilder, readiness

ROUNDS = 200  # long enough that a rule broken once in a while still shows up


def img(image_id, tags=(), categories=(), **kwargs):
    return Image(
        id=image_id,
        file=f"images/{image_id}.png",
        thumb=f"thumbs/{image_id}.jpg",
        tags=list(tags),
        categories=list(categories),
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
                images.append(img(f"{tag}{n}", [tag], [category]))
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
    animals = [img(tag, [tag], ["animals"]) for tag in ("cat", "dog", "bird", "fish", "horse")]
    vehicles = [img(tag, [tag], ["vehicles"]) for tag in ("car", "bus", "train", "boat")]
    return library(animals + vehicles, [question("q-cat", "cat")])


def test_same_category_draws_distractors_from_the_correct_images_category():
    builder = RoundBuilder(
        strategy_library(), Settings(option_count=4, distractor_strategy="same_category"), seed=2
    )
    for built in run(builder, 40):
        assert all("animals" in o.categories for o in built.options)


def test_contrast_draws_distractors_from_other_categories():
    builder = RoundBuilder(
        strategy_library(), Settings(option_count=4, distractor_strategy="contrast"), seed=2
    )
    for built in run(builder, 40):
        others = [o for o in built.options if o.id != built.correct.id]
        assert all("vehicles" in o.categories for o in others)


def test_a_strategy_falls_back_rather_than_ending_the_session():
    # Only two other animals exist, so n=5 cannot be filled from the category alone.
    images = [img(tag, [tag], ["animals"]) for tag in ("cat", "dog", "bird")]
    images += [img(tag, [tag], ["vehicles"]) for tag in ("car", "bus")]
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
    seen = {c for built in run(builder, 60) for o in built.options for c in o.categories}
    assert seen == {"animals", "vehicles"}


# -- strict categories (BACKLOG: a yellow dog is not a wrong answer) --------


def colour_library():
    """A yellow square and a yellow-ish dog. Tags cannot tell them apart: nothing
    records that the dog *looks* yellow, only that it is a dog."""
    images = [
        img("square-yellow", ["yellow"], ["colours", "shapes"]),
        img("square-blue", ["blue"], ["colours", "shapes"]),
        img("circle-red", ["red"], ["colours", "shapes"]),
        img("dog", ["dog"], ["animals"]),
        img("cat", ["cat"], ["animals"]),
    ]
    return library(images, [question("q-yellow", "yellow"), question("q-dog", "dog")])


def test_a_strict_category_keeps_a_colour_question_among_colours():
    builder = RoundBuilder(
        colour_library(),
        Settings(option_count=3, strict_categories=["colours"]),
        seed=11,
    )
    for built in run(builder, 40):
        if built.prompt.target_tag != "yellow":
            continue
        assert all("colours" in o.categories for o in built.options)


def test_a_category_nobody_marked_strict_still_crosses_freely():
    builder = RoundBuilder(colour_library(), Settings(option_count=3), seed=11)
    seen = {c for built in run(builder, 60) for o in built.options for c in o.categories}
    assert "animals" in seen and "colours" in seen


def test_strictness_only_binds_the_categories_it_names():
    """`colours` is strict; `animals` is not, so a dog question may still show a square
    — that is the easy day-one round SPEC §4.4 wants to keep."""
    builder = RoundBuilder(
        colour_library(),
        Settings(option_count=3, strict_categories=["colours"]),
        seed=3,
    )
    crossed = [
        built
        for built in run(builder, 80)
        if built.prompt.target_tag == "dog"
        and any("colours" in o.categories for o in built.options)
    ]
    assert crossed


def test_a_starved_strict_prompt_is_skipped_not_shortened():
    """Only one other colour exists, so a round of 3 cannot be built honestly. The
    prompt is skipped (SPEC §2.1 step 5) rather than padded with an animal."""
    images = [
        img("square-yellow", ["yellow"], ["colours"]),
        img("square-blue", ["blue"], ["colours"]),
        img("dog", ["dog"], ["animals"]),
        img("cat", ["cat"], ["animals"]),
    ]
    builder = RoundBuilder(
        library(images, [question("q-yellow", "yellow"), question("q-dog", "dog")]),
        Settings(option_count=3, strict_categories=["colours"]),
        seed=5,
    )
    for built in run(builder, 40):
        assert built.prompt.target_tag == "dog"
        assert len(built.options) == 3


def test_one_unbuildable_prompt_does_not_end_a_session_that_still_works():
    """The "never twice in a row" rule hides the last prompt from the next round. If
    everything else is unbuildable, repeat it rather than showing "all done" to a child
    sitting in front of a library that still has plenty in it."""
    images = [
        img("square-yellow", ["yellow"], ["colours"]),
        img("square-blue", ["blue"], ["colours"]),
        img("dog", ["dog"], ["animals"]),
        img("cat", ["cat"], ["animals"]),
    ]
    builder = RoundBuilder(
        library(images, [question("q-yellow", "yellow"), question("q-dog", "dog")]),
        Settings(option_count=3, strict_categories=["colours"]),
        seed=5,
    )
    assert len(run(builder, 30)) == 30  # never returns None, never ends early


def test_a_picture_can_be_in_several_categories_at_once():
    builder = RoundBuilder(
        colour_library(),
        Settings(option_count=2, enabled_categories=["shapes"]),
        seed=7,
    )
    # The squares are both colours and shapes, so enabling only `shapes` still finds them.
    for built in run(builder, 20):
        assert all("shapes" in o.categories for o in built.options)


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
        assert all("animals" in o.categories for o in built.options)


# -- readiness (SPEC §4.1) -------------------------------------------------


def test_readiness_is_happy_with_a_workable_library():
    ok, reason = readiness(basic(), Settings(option_count=2))
    assert ok
    assert "ready" in reason


def test_readiness_reports_an_empty_library():
    ok, reason = readiness(library([], []), Settings())
    assert not ok
    assert "No pictures" in reason


def test_readiness_reports_pictures_but_no_questions():
    images = [img("cat", ["cat"]), img("dog", ["dog"])]
    ok, reason = readiness(library(images, []), Settings())
    assert not ok
    assert "No questions" in reason


def test_readiness_names_the_tag_with_a_question_but_no_pictures():
    images = [img("cat", ["cat"]), img("dog", ["dog"])]
    ok, reason = readiness(library(images, [question("q", "truck")]), Settings())
    assert not ok
    assert "truck" in reason


def test_readiness_reports_too_few_pictures_for_n():
    images = [img("cat", ["cat"]), img("x", ["other"])]
    ok, reason = readiness(library(images, [question("q", "cat")]), Settings(option_count=4))
    assert not ok
    assert "4" in reason


def test_readiness_catches_a_library_that_only_fails_at_build_time():
    # Two pictures, but they share every tag, so no distractor is ever legal.
    images = [img("a", ["cat"]), img("b", ["cat"])]
    ok, reason = readiness(library(images, [question("q", "cat")]), Settings(option_count=2))
    assert not ok
    assert "Not enough different pictures" in reason


def test_readiness_does_not_disturb_the_real_session():
    # It builds a throwaway round to test; that must not consume state.
    lib = basic()
    settings = Settings(option_count=2)
    readiness(lib, settings)
    builder = RoundBuilder(lib, settings, seed=1)
    assert builder.build() is not None
