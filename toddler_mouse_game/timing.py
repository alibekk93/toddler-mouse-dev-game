"""Every timing constant in the app lives here, not as a magic number in an animation call.

Grows into the whole UX §3 table at M2.
"""

ESC_HOLD_MS = 3000  # SPEC §1: hold Esc this long to leave kid mode
RING_TICK_MS = 33  # ~30fps redraw of the Esc-hold ring
