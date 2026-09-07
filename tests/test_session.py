"""What a click does to the audio (SPEC §2.3, §2.4, UX §3).

Kid mode is judged by a human looking at it (ARCHITECTURE §5), but this rule is not
visual: clicking must cut the question off so the answer lands immediately, rather than
queueing the response behind a sentence that is still playing. A stub player records the
calls, so no audio backend is needed — this box has none.

Runs on the offscreen Qt platform, so it needs no display.
"""

import os
import random

import pytest
from conftest import make_image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from toddler_mouse_game.core import library as lib
from toddler_mouse_game.core.models import Settings, Sound
from toddler_mouse_game.core.round_builder import RoundBuilder
from toddler_mouse_game.ui.kid.scene import KidScene
from toddler_mouse_game.ui.kid.session import QuizSession, State


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakePlayer:
    """Records what the session asks for, in order."""

    def __init__(self) -> None:
        self.calls = []

    def play_voice(self, path):
        self.calls.append(("voice", str(path)))

    def stop_voice(self):
        self.calls.append(("stop_voice", None))

    def after_voice(self, callback):
        self.calls.append(("after_voice", None))
        callback()

    def stop_all(self):
        self.calls.append(("stop_all", None))

    def preload_all(self, paths):
        pass


class FakeSfx:
    def __init__(self) -> None:
        self.played = []

    def play(self, name, volume_scale=1.0):
        self.played.append(name)


def built_session(tmp_path, kinds=("praise", "retry")):
    """A one-round library with a question and, optionally, praise and retry lines."""
    library = lib.Library(root=tmp_path / "lib")
    # Distinct colours: identical pictures share a content hash and merge into one entry,
    # which would leave the round builder with nothing to use as a distractor.
    for name, colour in (("cat", (200, 60, 60)), ("truck", (60, 60, 200))):
        source = make_image(tmp_path / f"{name}.png", colour=colour)
        lib.add_image(library, source, tags=[name])
    library.sounds.append(
        Sound(id="q", kind="question", file="audio/questions/q.wav", target_tag="cat")
    )
    for kind in kinds:
        library.sounds.append(Sound(id=kind, kind=kind, file=f"audio/{kind}/{kind}.wav"))

    settings = Settings(option_count=2)
    scene = KidScene(settings.cursor_style, settings.cursor_scale)
    scene.setSceneRect(0, 0, 1920, 1080)
    player, sfx = FakePlayer(), FakeSfx()
    session = QuizSession(
        scene,
        library,
        settings,
        RoundBuilder(library, settings, seed=1),
        player,
        sfx,
    )
    session.start()
    session.state = State.WAITING  # skip the intro timers; the click rule is what matters
    return session, player, sfx


def card_for(session, correct: bool):
    target = session._round.correct.id
    return next(c for c in session.tiles() if (c.image_id == target) is correct)


def test_a_correct_click_cuts_the_question_and_answers_at_once(tmp_path, app):
    session, player, sfx = built_session(tmp_path)
    session.on_click(card_for(session, correct=True))

    assert player.calls[0] == ("stop_voice", None)
    assert "chime" in sfx.played
    # The praise line goes straight to the voice channel, not queued behind the question.
    assert ("after_voice", None) not in player.calls
    assert any(kind == "voice" and "praise" in path for kind, path in player.calls)


def test_a_wrong_click_cuts_the_question_and_nudges_at_once(tmp_path, app):
    session, player, sfx = built_session(tmp_path)
    session.on_click(card_for(session, correct=False))

    assert player.calls[0] == ("stop_voice", None)
    assert "nudge" in sfx.played
    assert any(kind == "voice" and "retry" in path for kind, path in player.calls)
    assert ("after_voice", None) not in player.calls


def test_a_click_on_the_background_touches_nothing(tmp_path, app):
    session, player, _sfx = built_session(tmp_path)
    session.on_click(None)
    assert player.calls == []


def test_a_second_click_while_celebrating_is_ignored_not_punished(tmp_path, app):
    session, player, sfx = built_session(tmp_path)
    session.on_click(card_for(session, correct=True))
    before = list(player.calls), list(sfx.played)
    session.on_click(card_for(session, correct=False))
    assert (player.calls, sfx.played) == before


def test_it_works_with_no_praise_or_retry_recorded(tmp_path, app):
    """A library with only questions still answers — the chime and nudge carry it."""
    session, player, sfx = built_session(tmp_path, kinds=())
    session.on_click(card_for(session, correct=True))
    assert player.calls == [("stop_voice", None)]
    assert "chime" in sfx.played


def test_the_question_is_replayed_after_a_wrong_click(tmp_path, app):
    """SPEC §2.4 step 4: 600ms later, ask again — after the retry line, not over it."""
    session, player, _sfx = built_session(tmp_path)
    session.on_click(card_for(session, correct=False))
    player.calls.clear()

    # Fire the pending one-shot timers by hand rather than sleeping.
    for timer in list(session._timers):
        timer.stop()
        timer.timeout.emit()
    assert ("after_voice", None) in player.calls
    assert any(kind == "voice" and "questions" in path for kind, path in player.calls)


def test_random_clicking_never_raises(tmp_path, app):
    """She will mash. Nothing here may throw, whatever order the clicks arrive in."""
    session, _player, _sfx = built_session(tmp_path)
    rng = random.Random(7)
    for _ in range(50):
        session.on_click(rng.choice([*session.tiles(), None]))


def test_cutting_the_voice_drops_what_was_queued_behind_it():
    """`after_voice` means "when this recording finishes". Cutting the recording makes
    that callback stale — leaving it set would fire it against whatever plays next."""
    from toddler_mouse_game.audio.player import Player

    player = Player()
    fired = []
    player._queued = lambda: fired.append("stale")  # as if queued behind the question
    player.stop_voice()
    player._check_voice()

    assert player._queued is None
    assert fired == []
