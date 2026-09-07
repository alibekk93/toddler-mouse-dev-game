"""The cursor clip rectangle (SPEC §7).

`ClipCursor` alters machine state, and getting its rectangle wrong does not fail loudly —
it silently traps the cursor in part of the screen, which reads as the game being broken.
The arithmetic is small enough to check exactly, so it is checked exactly.

Runs on the offscreen Qt platform, so it needs no display.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from toddler_mouse_game.ui.kid.window import physical_rect


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_an_unscaled_screen_maps_straight_through(app):
    assert physical_rect(QRect(0, 0, 1920, 1080), 1.0) == (0, 0, 1920, 1080)


def test_a_scaled_screen_is_reported_in_real_pixels(app):
    """The bug this exists for: at 150% Qt calls a 1920x1080 screen 1280x720. Clipping to
    those numbers pins the cursor inside the top-left two thirds of the display."""
    assert physical_rect(QRect(0, 0, 1280, 720), 1.5) == (0, 0, 1920, 1080)
    assert physical_rect(QRect(0, 0, 1536, 864), 1.25) == (0, 0, 1920, 1080)


def test_the_edges_are_exclusive_the_way_a_win32_rect_wants(app):
    """QRect's right/bottom are inclusive (1919), a Win32 RECT's are not (1920). Off by
    one pixel is survivable; off by one *scaled* pixel is how a clip drifts."""
    geometry = QRect(0, 0, 1920, 1080)
    assert geometry.right() == 1919 and geometry.bottom() == 1079
    assert physical_rect(geometry, 1.0)[2:] == (1920, 1080)


def test_a_screen_that_does_not_start_at_the_origin_keeps_its_offset(app):
    """A second display puts the primary screen's origin somewhere other than 0,0."""
    assert physical_rect(QRect(1920, 0, 1920, 1080), 1.0) == (1920, 0, 3840, 1080)
    assert physical_rect(QRect(-1280, 200, 1280, 720), 1.5) == (-1920, 300, 0, 1380)


def test_the_window_reports_a_clip_rect_without_being_shown(app):
    """`clip_rect` must not depend on the window having finished going fullscreen — that
    dependency was the other half of the bug."""
    from toddler_mouse_game.ui.kid.window import KidWindow

    window = KidWindow()
    rect = window.clip_rect()
    assert rect is not None
    left, top, right, bottom = rect
    assert right > left and bottom > top
