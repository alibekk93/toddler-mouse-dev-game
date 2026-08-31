"""The quiz: one round after another, forever, until a grown-up exits.

State machine (ARCHITECTURE §3): IDLE -> INTRO -> ASKING -> WAITING -> CELEBRATING ->
INTRO(next), plus FINISHED. The repeat clock, hint escalation, idle handling and the
"all done" screen are M4; this is the playable loop.

Every pending transition is a one-shot QTimer owned here and cancelled on state exit.
Nothing sleeps, nothing blocks.

**Nothing in here can punish her.** A wrong click wobbles the card, plays a note
quieter than the right answer's, and asks again. Everything stays on screen and stays
clickable; she can click the same wrong card ten times and get the same gentle answer
ten times.
"""

from enum import Enum, auto

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from ...timing import (
    CARD_APPEAR_MS,
    CARD_STAGGER_MS,
    CROSSFADE_MS,
    QUESTION_DELAY_MS,
    REPLAY_AFTER_WRONG_MS,
)
from .card import Card
from .layout import slots


class State(Enum):
    IDLE = auto()
    INTRO = auto()
    ASKING = auto()
    WAITING = auto()
    CELEBRATING = auto()
    FINISHED = auto()


class QuizSession(QObject):
    """Owns the round loop. `finished` means the library ran out of usable content."""

    finished = Signal()

    def __init__(self, scene, library, settings, builder, player, sfx, parent=None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._library = library
        self._settings = settings
        self._builder = builder
        self._player = player
        self._sfx = sfx

        self.state = State.IDLE
        self._round = None
        self._cards: list[Card] = []
        self._timers: list[QTimer] = []
        self._pixmaps: dict[str, QPixmap] = {}

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._next_round()

    def stop(self) -> None:
        self._cancel_timers()
        self._player.stop_all()
        self._clear_cards()
        self.state = State.IDLE

    def tiles(self):
        return list(self._cards)

    def tick(self, elapsed_ms: int) -> None:
        for card in self._cards:
            card.tick(elapsed_ms)

    # -- timers ------------------------------------------------------------

    def _after(self, ms: int, callback) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(lambda: self._timers.remove(timer) if timer in self._timers else None)
        self._timers.append(timer)
        timer.start(max(0, int(ms)))

    def _cancel_timers(self) -> None:
        for timer in self._timers:
            timer.stop()
        self._timers.clear()

    # -- rounds ------------------------------------------------------------

    def _clear_cards(self) -> None:
        for card in self._cards:
            self._scene.removeItem(card)
        self._cards.clear()

    def _pixmap_for(self, image) -> QPixmap:
        if image.id not in self._pixmaps:
            self._pixmaps[image.id] = QPixmap(str(self._library.root / image.file))
        return self._pixmaps[image.id]

    def _next_round(self) -> None:
        self._cancel_timers()
        self._clear_cards()

        built = self._builder.build()
        if built is None:
            # No prompt can make a round. M4 gives this a calm "all done" screen.
            self.state = State.FINISHED
            self.finished.emit()
            return

        self._round = built
        self.state = State.INTRO

        rect = self._scene.sceneRect()
        positions = slots(len(built.options), rect.width(), rect.height())
        for index, (image, (x, y, w, _h)) in enumerate(zip(built.options, positions)):
            card = Card(w, self._pixmap_for(image), image.id)
            card.place(x, y, w)
            card.appear(delay_ms=index * CARD_STAGGER_MS)  # staggered, left to right
            self._scene.addItem(card)
            self._cards.append(card)
            self._after(index * CARD_STAGGER_MS, lambda: self._sfx.play("whoosh", 0.5))

        self._after(QUESTION_DELAY_MS, self._ask)

    def _ask(self) -> None:
        self.state = State.ASKING
        self._play_question()
        self._after(CARD_APPEAR_MS, self._begin_waiting)

    def _begin_waiting(self) -> None:
        if self.state in (State.CELEBRATING, State.FINISHED):
            return
        self.state = State.WAITING

    def _play_question(self) -> None:
        if self._round is None:
            return
        self._player.play_voice(self._library.root / self._round.prompt.file)

    # -- input -------------------------------------------------------------

    def on_hover(self, tile) -> None:
        """The hover reaction is the entire mouse lesson, and it runs constantly."""
        if tile is not None and self.state in (State.ASKING, State.WAITING):
            self._sfx.play("tick")

    def on_click(self, tile) -> None:
        if self._round is None or tile not in self._cards:
            return  # clicking the background does nothing at all
        if self.state not in (State.ASKING, State.WAITING):
            return  # already celebrating; further clicks are ignored, not punished

        if tile.image_id == self._round.correct.id:
            self._correct(tile)
        else:
            self._wrong(tile)

    # -- responses ---------------------------------------------------------

    def _correct(self, card: Card) -> None:
        self.state = State.CELEBRATING
        self._cancel_timers()

        card.setZValue(10)
        card.celebrate_to(self._scene.centre(), self._celebrate_scale(card))
        for other in self._cards:
            if other is not card:
                other.set_hovering(False)
                other.recede()

        def sing() -> None:
            self._sfx.play("chime")
            praise = self._library.playable_sounds("praise")
            if praise:
                # A parent's "yes! that's the cat!" beats a chime every time.
                chosen = self._builder._rng.choice(praise)
                self._player.after_voice(
                    lambda: self._player.play_voice(self._library.root / chosen.file)
                )

        # Never cut audio off: if the question is still playing, let it finish (UX §3).
        self._player.after_voice(sing)

        hold = int(self._settings.celebrate_duration * 1000)
        self._after(hold + CROSSFADE_MS, self._next_round)

    def _celebrate_scale(self, card: Card) -> float:
        """Always a visible growth, whatever n is.

        At n=2 a card already fills 55% of the height, so a target expressed as a
        fraction of the screen would mean no growth at all. Grow by a factor instead,
        capped so the card still fits on screen.
        """
        rect = self._scene.sceneRect()
        fits = min(rect.width(), rect.height()) * 0.72 / max(card.side, 1.0)
        return max(1.0, min(1.45, fits))

    def _wrong(self, card: Card) -> None:
        """Never harsh. Nothing shrinks, disappears, or is taken away (SPEC §2.4)."""
        card.wobble()
        self._sfx.play("nudge")

        retry = self._library.playable_sounds("retry")
        if retry:
            chosen = self._builder._rng.choice(retry)
            self._player.after_voice(
                lambda: self._player.play_voice(self._library.root / chosen.file)
            )

        # Ask again, once whatever is talking has finished.
        self._after(REPLAY_AFTER_WRONG_MS, lambda: self._player.after_voice(self._play_question))
