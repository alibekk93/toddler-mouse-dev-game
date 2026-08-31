"""Where the cards go. Pure Python — no Qt, so the geometry rules are testable.

UX §1 fixes the grid per n, and three rules that hold at every n:

- cards are sized as a fraction of screen **height**;
- the gap between neighbours is at least 8% of screen width, because her aim is
  terrible and adjacent targets must not be reachable by a 3px slip;
- nothing comes within 5% of a screen edge, where the cursor gets clamped.

Everything is a fraction of the scene rect, never a fixed pixel (CLAUDE.md).
"""

MIN_GAP_W = 0.08  # of screen width
MIN_MARGIN = 0.05  # of the shorter screen edge

# n -> (rows, columns per row, card height as a fraction of screen height)
LAYOUTS: dict[int, tuple[tuple[int, ...], float]] = {
    2: ((2,), 0.55),
    3: ((3,), 0.42),
    4: ((2, 2), 0.40),
    5: ((3, 2), 0.33),  # top three, bottom two, each row centred
    6: ((3, 3), 0.33),
}


def slots(n: int, width: float, height: float) -> list[tuple[float, float, float, float]]:
    """Return n (x, y, w, h) rectangles, left to right then top to bottom.

    Cards are square. If the ideal size from UX §1 would break the gap or margin
    rules on this screen, every card shrinks until it fits — the rules win, because
    they are about whether she can hit the thing she is aiming at.
    """
    if n not in LAYOUTS:
        raise ValueError(f"no layout for n={n}")
    rows, size_fraction = LAYOUTS[n]

    margin = MIN_MARGIN * min(width, height)
    gap = MIN_GAP_W * width
    widest = max(rows)

    side = size_fraction * height
    # Shrink to fit the widest row, then to fit all the rows stacked.
    side = min(side, (width - 2 * margin - gap * (widest - 1)) / widest)
    side = min(side, (height - 2 * margin - gap * (len(rows) - 1)) / len(rows))
    side = max(side, 1.0)

    block_height = side * len(rows) + gap * (len(rows) - 1)
    top = (height - block_height) / 2

    out: list[tuple[float, float, float, float]] = []
    for row_index, count in enumerate(rows):
        row_width = side * count + gap * (count - 1)
        left = (width - row_width) / 2  # every row is centred, which is what n=5 needs
        y = top + row_index * (side + gap)
        for column in range(count):
            out.append((left + column * (side + gap), y, side, side))
    return out
