"""Every timing constant in the app lives here, not as a magic number in an animation call.

The numbers come from UX §3. Everything is slower than an adult app on purpose:
nothing that matters happens fast.
"""

# Leaving kid mode (SPEC §1)
ESC_HOLD_MS = 3000
RING_TICK_MS = 33  # ~30fps redraw of the Esc-hold ring

# The frame clock for drifting and idle animation
FRAME_MS = 16  # ~60fps, the performance target in ARCHITECTURE §6

# Cards appearing (UX §3)
CARD_APPEAR_MS = 500
CARD_STAGGER_MS = 120  # left to right
QUESTION_DELAY_MS = 300  # after the first card appears
CROSSFADE_MS = 400  # to the next round

# Hover and press (UX §2)
HOVER_SCALE_MS = 150
HOVER_SCALE = 1.08
PRESS_SCALE = 0.96
CURSOR_HOVER_GROW = 1.15
CURSOR_PRESS_SQUASH = 0.85
HOVER_TICK_MIN_GAP_MS = 150  # so sweeping six cards doesn't machine-gun

# Responses (SPEC §2.3, §2.4)
WOBBLE_MS = 400  # wrong-answer head-shake
WOBBLE_DEGREES = 6.0
REPLAY_AFTER_WRONG_MS = 600
CELEBRATE_MS = 2500  # default; overridden by the celebrate_duration setting
CLICK_DEBOUNCE_MS = 400  # the second click of a rapid burst is discarded (UX §2)

# The cursor's own idle life (UX §2, §5)
CURSOR_BREATH_MS = 2400
CURSOR_BREATH_SCALE = 0.04

# Warm-up (SPEC §3)
SHAPE_CROSS_SECONDS = (15.0, 25.0)  # slow enough to be a target, not a chase
SHAPE_RESPAWN_MS = 1500
POP_MS = 320
