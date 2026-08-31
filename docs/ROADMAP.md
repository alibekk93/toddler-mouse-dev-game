# Roadmap

Build order matters here. The goal of the early milestones is to get a playable thing in front of her fast, because her actual reactions will change the design more than any amount of speccing will.

---

## M0 — Skeleton
Project scaffold in `toddler-mouse-dev-game/`, `pyproject.toml`, dependencies pinned, `.gitignore` (per `CLAUDE.md` rule 7 — do this first, before any test content exists to leak), `core/models.py` dataclasses, `core/settings.py` with defaults, empty PySide6 app that opens a parent window and can switch to a blank fullscreen kid window and back via the `Esc` hold.

**Done when:** the mode switch works and the `Esc`-hold ring behaves.

## M1 — Library core (no UI)
`core/library.py`, `core/importer.py`, `core/round_builder.py`. Full test suite from `ARCHITECTURE.md` §5. A CLI helper (`python -m toddler_mouse_game.tools.seed`) that imports folders of images and recordings, with tags passed on the command line — the CLI form of the staging tray's tag field (§4.2), never guessed from a filename. Its `--demo` mode generates a whole working library from nothing (shapes, colours, and placeholder tones), so a test library exists before any UI does.

Audio normalisation (trim, peak-normalise) is **not** here: M1 adopts WAVs as-is and only measures them. It lands in M3 beside the recorder, which is its only caller and the only place a person can hear whether the trim ate a softly-spoken first word.

**Done when:** `pytest` passes and a hand-built library folder loads, validates, and produces valid rounds on demand.

## M2 — Warm-up, then playable quiz
Two deliverables, in this order.

**Warm-up first** (`SPEC.md` §3): sprite cursor, hover reactions, drifting shapes, popping. It needs no library, no audio pipeline, and no round logic, which makes it both the fastest route to something real on screen and the cleanest place to get the cursor feeling right.

**Then the quiz**: cards, layout for n=2 and n=4, click resolution, correct/wrong responses, question audio playback, round-to-round transitions. Placeholder sfx are fine.

Also the minimum session hardening from `SPEC.md` §7 — keep the display awake and clip the cursor to the window. Without those, the first real ten-minute session ends with a dimmed screen or a cursor lost behind the taskbar.

**Done when:** she can sit down and use warm-up, and then play the quiz with a hand-seeded library.

> **Put it in front of her here.** Watch what she does with the mouse before building anything else. Expect surprises: which cursor she tracks, whether she lifts the mouse off the desk, whether hover registers at all, whether n=2 is already too many.

## M3 — Parent content tools
Images page (file dialog, drag-drop, clipboard paste, staging tray, tagging, bulk tag). Sounds page (record, level meter, playback, trim, keep/re-record, target-tag autocomplete), including the grouping and prompting that push toward several recordings per tag (`SPEC.md` §4.3). Play page with the readiness check and both activity buttons.

**Done when:** a complete library can be built without touching the filesystem.

## M4 — Polish pass
All n from 2 to 6, the repeat clock and hint escalation, idle and attention handling, confetti, real sound design, celebration animation, "all done" screen, focus-loss pause, reduced-motion mode.

**Done when:** the kid-mode manual checklist passes.

## M5 — Settings, stats, backup, robustness
Settings page, distractor strategies, stats logging including the motor metrics, the Progress page (words table + three mouse-control numbers), library export/import with verification and the every-20-additions reminder, full validation/repair UI, atomic saves with `.bak` rotation, the remaining session hardening (Sticky/Filter Keys suppression and crash-safe restoration), graceful handling of every row in `SPEC.md` §6.

**Done when:** deliberately corrupting the library folder in five different ways yields five clear warnings and zero crashes, an exported zip restores cleanly into an empty folder, and killing the process mid-session leaves the machine untouched.

## M6 — Ship
PyInstaller one-dir build, desktop shortcut, first-run experience that creates an empty library and points at the Images page (with Warm-up playable immediately, since it needs no content), short parent README covering "how to add a picture" and "how to get out of the game".

**Done when:** it runs on the target machine from a shortcut, with no Python installed by hand.

---

Longer-term ideas that are deliberately out of scope live in `docs/FUTURE_IDEAS.md`.