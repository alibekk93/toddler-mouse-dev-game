# Roadmap

Build order matters here. The goal of the early milestones is to get a playable thing in front of her fast, because her actual reactions will change the design more than any amount of speccing will.

---

## M0 — Skeleton
Project scaffold in `toddler-mouse-dev-game/`, `pyproject.toml`, dependencies pinned, `.gitignore` (per `CLAUDE.md` rule 7 — do this first, before any test content exists to leak), `core/models.py` dataclasses, `core/settings.py` with defaults, empty PySide6 app that opens a parent window and can switch to a blank fullscreen kid window and back via the `Esc` hold.

**Done when:** the mode switch works and the `Esc`-hold ring behaves.

## M1 — Library core (no UI)
`core/library.py`, `core/importer.py`, `core/round_builder.py`. Full test suite from `ARCHITECTURE.md` §5. A CLI helper (`python -m toddler_mouse_game.tools.seed`) that imports a folder of images with tags from filenames, so a test library exists before any UI does.

**Done when:** `pytest` passes and a hand-built library folder loads, validates, and produces valid rounds on demand.

## M2 — Playable kid mode
Cards, layout for n=2 and n=4, hover/press reactions, sprite cursor, click resolution, correct/wrong responses, question audio playback, round-to-round transitions. Placeholder sfx are fine.

**Done when:** she can sit down and play with a hand-seeded library.

> **Put it in front of her here.** Watch what she does with the mouse before building anything else. Expect surprises: which cursor she tracks, whether she lifts the mouse off the desk, whether hover registers at all, whether n=2 is already too many.

## M3 — Parent content tools
Images page (file dialog, drag-drop, clipboard paste, staging tray, tagging, bulk tag). Sounds page (record, level meter, playback, trim, keep/re-record, target-tag autocomplete). Play page with the readiness check.

**Done when:** a complete library can be built without touching the filesystem.

## M4 — Polish pass
All n from 2 to 6, hint escalation, idle and attention handling, confetti, real sound design, celebration animation, "all done" screen, focus-loss pause, reduced-motion mode.

**Done when:** the kid-mode manual checklist passes.

## M5 — Settings, stats, robustness
Settings page, distractor strategies, stats logging and the Progress page, full validation/repair UI, atomic saves with `.bak` rotation, graceful handling of every row in `SPEC.md` §5.

**Done when:** deliberately corrupting the library folder in five different ways yields five clear warnings and zero crashes.

## M6 — Ship
PyInstaller one-dir build, desktop shortcut, first-run experience that creates an empty library and points at the Images page, short parent README covering "how to add a picture" and "how to get out of the game".

**Done when:** it runs on the target machine from a shortcut, with no Python installed by hand.

---

## Later, maybe

Only after months of real use, and only if she asks for it by her behaviour:

- **Sequence mode** — "find the cat, then the dog" (two-step working memory).
- **Difficulty drift** — auto-raise `n` for tags with consistently high first-click accuracy.
- **Sibling libraries** — profile picker instead of a `--library` flag.
- **Click-and-drag mode** — drag the cat to the basket. A genuinely harder motor skill and a natural sequel.
- **Optional TTS fallback** for tags with no recording, off by default.