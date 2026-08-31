"""Warm-up invariants that would otherwise break silently (SPEC §3, UX §6).

Kid mode is checked by a human looking at it (ARCHITECTURE §5), but these three rules
are geometric and cheap to assert: shapes stay inside the 5% margin, they never overlap
(so a click always has one unambiguous owner), and a popped shape comes back.

Runs on the offscreen Qt platform, so it needs no display.
"""

import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from toddler_mouse_game.core.models import Settings
from toddler_mouse_game.timing import SHAPE_RESPAWN_MS
from toddler_mouse_game.ui.kid.scene import KidScene
from toddler_mouse_game.ui.kid.warmup import MARGIN, WarmupActivity

WIDTH, HEIGHT = 1920, 1080


class FakeSfx:
    def __init__(self):
        self.played = []

    def play(self, name, volume_scale=1.0):
        self.played.append(name)


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def warmup(qt_app, request):
    count = getattr(request, "param", 6)
    scene = KidScene()
    scene.set_size(WIDTH, HEIGHT)
    settings = Settings(warmup_shape_count=count)
    activity = WarmupActivity(scene, settings, FakeSfx(), rng=random.Random(7))
    activity.start()
    return activity


def check_invariants(activity, note=""):
    margin = MARGIN * min(WIDTH, HEIGHT)
    live = activity.tiles()
    for shape in live:
        x, y, half = shape.pos().x(), shape.pos().y(), shape.side / 2
        assert x - half >= margin - 1, f"{note}: crossed the left margin"
        assert y - half >= margin - 1, f"{note}: crossed the top margin"
        assert x + half <= WIDTH - margin + 1, f"{note}: crossed the right margin"
        assert y + half <= HEIGHT - margin + 1, f"{note}: crossed the bottom margin"
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            distance = ((a.pos().x() - b.pos().x()) ** 2 + (a.pos().y() - b.pos().y()) ** 2) ** 0.5
            assert distance >= (a.side + b.side) / 2 * 0.95, f"{note}: shapes overlap"


@pytest.mark.parametrize("warmup", [4, 5, 6, 7, 8], indirect=True)
def test_shapes_respect_the_margin_and_never_overlap_while_drifting(warmup):
    check_invariants(warmup, "at rest")
    for second in range(20):  # 20s of drift, including bounces off every edge
        for _ in range(60):
            warmup.tick(16)
        check_invariants(warmup, f"t={second + 1}s")


def test_shape_count_is_clamped_to_four_through_eight(qt_app):
    for asked, expected in ((1, 4), (4, 4), (8, 8), (99, 8)):
        scene = KidScene()
        scene.set_size(WIDTH, HEIGHT)
        activity = WarmupActivity(scene, Settings(warmup_shape_count=asked), FakeSfx())
        activity.start()
        assert len(activity.tiles()) == expected


def test_a_popped_shape_bursts_and_comes_back(warmup):
    sfx = warmup._sfx
    before = len(warmup.tiles())
    shape = warmup.tiles()[0]

    warmup.on_click(shape)
    assert shape.popped
    assert len(warmup.tiles()) == before - 1
    assert "pop" in sfx.played

    for _ in range(int(SHAPE_RESPAWN_MS / 16) + 10):
        warmup.tick(16)
    assert len(warmup.tiles()) == before, "the shape never came back"
    check_invariants(warmup, "after respawn")


def test_clicking_the_background_does_nothing_at_all(warmup):
    sfx = warmup._sfx
    sfx.played.clear()
    before = len(warmup.tiles())
    warmup.on_click(None)
    assert len(warmup.tiles()) == before
    assert sfx.played == []  # silently, per UX §6


def test_hovering_a_shape_ticks_and_scales_it(warmup):
    shape = warmup.tiles()[0]
    shape.set_hovering(True)
    warmup.on_hover(shape)
    for _ in range(30):
        warmup.tick(16)
    assert shape.scale() > 1.05  # 108%, same as a quiz card
    assert "tick" in warmup._sfx.played


def test_warmup_needs_no_library_at_all(qt_app):
    """It must stay runnable on a completely empty library (CLAUDE.md conventions)."""
    scene = KidScene()
    scene.set_size(WIDTH, HEIGHT)
    activity = WarmupActivity(scene, Settings(), FakeSfx())
    activity.start()
    for _ in range(120):
        activity.tick(16)
    assert len(activity.tiles()) == 6
    activity.stop()
    assert activity.tiles() == []
