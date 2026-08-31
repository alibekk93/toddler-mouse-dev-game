"""Session hardening (SPEC §7). Windows-only ctypes; a silent no-op everywhere else.

Windows will end a play session on its own: the display dims while she studies a card,
or the cursor escapes to a corner and is lost behind the taskbar. Both defences are
applied on entering kid mode and released on leaving it.

**Restoration matters more than application.** Every call here alters machine state, so
a crash must not leave the machine with a clipped cursor. Two belts: the context manager
releases on any exception, and an `atexit` hook releases whatever is still held if the
process dies another way. If a defence cannot be applied, we log it and carry on — not
being able to keep the display awake is not a reason to refuse to play.

Sticky/Filter Keys suppression is deliberately not here yet; it lands at M5 with the
rest of the hardening.
"""

import atexit
import ctypes
import sys
from contextlib import contextmanager

IS_WINDOWS = sys.platform == "win32"

ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002
ES_SYSTEM_REQUIRED = 0x00000001

_held: set[str] = set()  # what is currently applied, so atexit can undo exactly that
_failures: list[str] = []


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _user32():
    return ctypes.windll.user32  # type: ignore[attr-defined]


def _kernel32():
    return ctypes.windll.kernel32  # type: ignore[attr-defined]


# -- display ---------------------------------------------------------------


def keep_display_awake() -> bool:
    """Stop the screen dimming or sleeping for the length of the session."""
    if not IS_WINDOWS:
        return False
    try:
        _kernel32().SetThreadExecutionState(
            ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
        )
        _held.add("display")
        return True
    except Exception as exc:  # noqa: BLE001 - a failed defence must never stop play
        _failures.append(f"could not keep the display awake: {exc}")
        return False


def release_display() -> None:
    """Hand power management back. Never leave a machine unable to sleep."""
    if not IS_WINDOWS or "display" not in _held:
        return
    try:
        _kernel32().SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:  # noqa: BLE001, S110 - release runs from atexit; never raise here
        pass
    _held.discard("display")


# -- cursor ----------------------------------------------------------------


def clip_cursor(left: int, top: int, right: int, bottom: int) -> bool:
    """Confine the cursor to the game window so it cannot be lost off-screen."""
    if not IS_WINDOWS:
        return False
    try:
        rect = _Rect(int(left), int(top), int(right), int(bottom))
        if not _user32().ClipCursor(ctypes.byref(rect)):
            raise OSError(ctypes.get_last_error())
        _held.add("cursor")
        return True
    except Exception as exc:  # noqa: BLE001
        _failures.append(f"could not confine the cursor: {exc}")
        return False


def release_cursor() -> None:
    """Free the cursor. A clipped cursor with the app frozen is a broken machine."""
    if not IS_WINDOWS or "cursor" not in _held:
        return
    try:
        _user32().ClipCursor(None)
    except Exception:  # noqa: BLE001, S110 - release runs from atexit; never raise here
        pass
    _held.discard("cursor")


# -- lifecycle -------------------------------------------------------------


def release_all() -> None:
    """Undo everything currently held. Safe to call repeatedly, and from atexit."""
    release_cursor()
    release_display()


atexit.register(release_all)


def failures() -> list[str]:
    """What could not be applied, for the caller to log. Never raised at the player."""
    return list(_failures)


@contextmanager
def hardened_session(cursor_rect: tuple[int, int, int, int] | None = None):
    """Hold the session defences for as long as kid mode is on screen."""
    _failures.clear()
    keep_display_awake()
    if cursor_rect is not None:
        clip_cursor(*cursor_rect)
    try:
        yield
    finally:
        release_all()  # runs on a normal exit and on any exception alike
