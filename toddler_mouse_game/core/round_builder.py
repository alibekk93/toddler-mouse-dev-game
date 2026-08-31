"""Build one round: a question, a correct picture, and n-1 distractors. SPEC §2.1.

Pure Python — no Qt, no display. This is the part of the game that can actually be
tested: you cannot write a meaningful test for a toddler's click, but you can absolutely
test that the correct answer never lands in the same slot twice running.

Selection is deliberately legible rather than clever. FUTURE_IDEAS argues at length
against tuning a spaced-repetition scheduler for a two-year-old: if she is seeing too
much of something, a parent should be able to see why immediately.
"""

import random
from collections import deque
from dataclasses import dataclass

from .library import Library
from .models import Image, Settings, Sound

MIN_OPTIONS = 2
MAX_OPTIONS = 6
RECENT_PROMPTS = 10  # how far back "recently used" reaches, in rounds
RECENT_IMAGES = 10


@dataclass(slots=True)
class Round:
    """One question. `options` is what goes on screen, left to right."""

    prompt: Sound
    correct: Image
    options: list[Image]
    correct_index: int


class RoundBuilder:
    """Stateful because the rules are: what came last shapes what comes next.

    Pass `seed` for a deterministic sequence — that is what makes the "never the same
    slot twice" and "never the same prompt twice" rules testable over a long run.
    """

    def __init__(self, library: Library, settings: Settings, seed: int | None = None) -> None:
        self._library = library
        self._settings = settings
        self._rng = random.Random(seed)
        self._recent_prompts: deque[str] = deque(maxlen=RECENT_PROMPTS)
        self._recent_images: deque[str] = deque(maxlen=RECENT_IMAGES)
        self._last_correct_index: int | None = None

    # -- public ------------------------------------------------------------

    @property
    def option_count(self) -> int:
        return max(MIN_OPTIONS, min(MAX_OPTIONS, self._settings.option_count))

    def build(self) -> Round | None:
        """Next round, or None when no prompt can produce one (SPEC §6, "all done")."""
        remaining = self._candidate_prompts()
        while remaining:
            prompt = self._pick(remaining, self._recent_prompts, lambda s: s.id)
            remaining.remove(prompt)
            built = self._build_for(prompt)
            if built is not None:
                self._remember(built)
                return built
        return None

    # -- selection ---------------------------------------------------------

    def _usable_images(self) -> list[Image]:
        """Enabled, unbroken, and inside the enabled categories (SPEC §4.4)."""
        images = self._library.playable_images()
        allowed = self._settings.enabled_categories
        if allowed is None:
            return images
        return [i for i in images if i.category in set(allowed)]

    def _candidate_prompts(self) -> list[Sound]:
        """Questions whose tag has at least one usable picture behind it."""
        tags = {tag for image in self._usable_images() for tag in image.tags}
        prompts = [
            s
            for s in self._library.playable_sounds("question")
            if s.target_tag and s.target_tag in tags
        ]
        # Never the same prompt twice in a row — unless it is the only one there is.
        if len(prompts) > 1 and self._recent_prompts:
            last = self._recent_prompts[-1]
            prompts = [s for s in prompts if s.id != last] or prompts
        return prompts

    def _weight(self, key: str, recent: deque[str]) -> float:
        """Recently used means less likely, never impossible.

        The most recent entry gets the smallest weight and the oldest gets nearly 1, so
        a tag's several recordings rotate for free: the one just heard is the least
        likely to come next, and the ones she hasn't heard in a while float back up.
        """
        try:
            age = len(recent) - list(recent).index(key)  # 1 = used most recently
        except ValueError:
            return 1.0
        return age / (len(recent) + 1)

    def _pick(self, items: list, recent: deque[str], key) -> object:
        weights = [self._weight(key(item), recent) for item in items]
        return self._rng.choices(items, weights=weights, k=1)[0]

    def _distractor_pool(self, correct: Image, target_tag: str) -> list[Image]:
        """Images that share nothing with the correct answer.

        Excluding every tag the correct image carries — not just the target tag — is
        what stops a dog turning up as a distractor for "where is the animal?".
        An untagged image trivially qualifies, which is DATA_MODEL §3's "never a
        correct answer, may still be a distractor".
        """
        correct_tags = set(correct.tags)
        pool = [
            i
            for i in self._usable_images()
            if i.id != correct.id and target_tag not in i.tags and not correct_tags & set(i.tags)
        ]

        strategy = self._settings.distractor_strategy
        if strategy == "same_category":
            preferred = [i for i in pool if i.category == correct.category]
        elif strategy == "contrast":
            preferred = [i for i in pool if i.category != correct.category]
        else:  # mixed, the default and the easiest
            return pool
        # A strategy narrows the pool; it never makes a round impossible.
        return preferred if len(preferred) >= self.option_count - 1 else pool

    def _build_for(self, prompt: Sound) -> Round | None:
        target_tag = prompt.target_tag
        candidates = [i for i in self._usable_images() if target_tag in i.tags]
        if not candidates:
            return None
        # Variety matters: she should learn "cat" the concept, not one cat picture.
        correct = self._pick(candidates, self._recent_images, lambda i: i.id)

        pool = self._distractor_pool(correct, target_tag)
        needed = self.option_count - 1
        if len(pool) < needed:
            return None
        options = [correct, *self._rng.sample(pool, needed)]

        self._rng.shuffle(options)
        index = next(i for i, image in enumerate(options) if image.id == correct.id)
        if index == self._last_correct_index and len(options) > 1:
            # Otherwise she learns "always the left one" instead of learning the word.
            swap = self._rng.choice([i for i in range(len(options)) if i != index])
            options[index], options[swap] = options[swap], options[index]
            index = swap

        return Round(prompt=prompt, correct=correct, options=options, correct_index=index)

    def _remember(self, built: Round) -> None:
        self._recent_prompts.append(built.prompt.id)
        self._recent_images.append(built.correct.id)
        self._last_correct_index = built.correct_index
