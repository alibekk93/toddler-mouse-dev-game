"""Card geometry (UX §1). No Qt, no display."""

import pytest

from toddler_mouse_game.ui.kid.layout import LAYOUTS, MIN_GAP_W, MIN_MARGIN, slots

SCREENS = [(1920, 1080), (1366, 768), (2560, 1440), (1280, 1024)]


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def gap_between(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(bx - (ax + aw), ax - (bx + bw))
    dy = max(by - (ay + ah), ay - (by + bh))
    return max(dx, dy)


@pytest.mark.parametrize("n", sorted(LAYOUTS))
@pytest.mark.parametrize(("width", "height"), SCREENS)
def test_every_card_is_placed(n, width, height):
    rects = slots(n, width, height)
    assert len(rects) == n


@pytest.mark.parametrize("n", sorted(LAYOUTS))
@pytest.mark.parametrize(("width", "height"), SCREENS)
def test_cards_never_touch_the_screen_edge(n, width, height):
    margin = MIN_MARGIN * min(width, height)
    for x, y, w, h in slots(n, width, height):
        assert x >= margin - 0.5
        assert y >= margin - 0.5
        assert x + w <= width - margin + 0.5
        assert y + h <= height - margin + 0.5


@pytest.mark.parametrize("n", sorted(LAYOUTS))
@pytest.mark.parametrize(("width", "height"), SCREENS)
def test_neighbours_keep_the_minimum_gap(n, width, height):
    rects = slots(n, width, height)
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            assert not overlap(a, b)
            assert gap_between(a, b) >= MIN_GAP_W * width - 0.5


@pytest.mark.parametrize("n", sorted(LAYOUTS))
def test_cards_are_square_and_all_the_same_size(n):
    rects = slots(n, 1920, 1080)
    sides = {round(w, 6) for _, _, w, _ in rects}
    assert len(sides) == 1
    for _, _, w, h in rects:
        assert w == pytest.approx(h)


@pytest.mark.parametrize("n", sorted(LAYOUTS))
def test_the_block_is_centred(n):
    width, height = 1920, 1080
    rects = slots(n, width, height)
    left = min(x for x, _, _, _ in rects)
    right = max(x + w for x, _, w, _ in rects)
    top = min(y for _, y, _, _ in rects)
    bottom = max(y + h for _, y, _, h in rects)
    assert (left + right) / 2 == pytest.approx(width / 2)
    assert (top + bottom) / 2 == pytest.approx(height / 2)


def test_n5_is_three_over_two_each_row_centred():
    rects = slots(5, 1920, 1080)
    top_row = [r for r in rects if r[1] == min(r[1] for r in rects)]
    bottom_row = [r for r in rects if r not in top_row]
    assert len(top_row) == 3 and len(bottom_row) == 2
    for row in (top_row, bottom_row):
        centre = (min(x for x, _, _, _ in row) + max(x + w for x, _, w, _ in row)) / 2
        assert centre == pytest.approx(960)


def test_a_cramped_screen_shrinks_the_cards_rather_than_breaking_the_rules():
    # 6 cards at 8% gaps need most of the width; the cards must give, not the gaps.
    rects = slots(6, 800, 600)
    assert all(w > 1 for _, _, w, _ in rects)
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            assert not overlap(a, b)


def test_unknown_n_is_rejected():
    with pytest.raises(ValueError):
        slots(7, 1920, 1080)
