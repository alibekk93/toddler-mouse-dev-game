# CLAUDE.md

Project instructions for Claude Code sessions on **Where Is It?**

## What this is

An offline PySide6 desktop game that teaches a 2-year-old to use a mouse. A recorded parent voice asks "where is the cat?", n pictures appear, she clicks the cat. All content is parent-supplied: tagged images and recorded questions in a plain folder with a JSON manifest.

Read `docs/SPEC.md` before changing behaviour, `docs/UX.md` before changing anything in kid mode, `docs/DATA_MODEL.md` before touching storage, `docs/ARCHITECTURE.md` before adding a dependency. `docs/ROADMAP.md` has the build order.

## Commands

Repo root is `buska-game/toddler-mouse-dev-game/`. The package is `toddler_mouse_game`.

```bash
python -m venv .venv && .venv\Scripts\activate                    # Windows
pip install -e ".[dev]"
python -m toddler_mouse_game --library ../library                 # parent mode, real content
python -m toddler_mouse_game --kid --library ./testlib            # straight into kid mode, test content
pytest                                                            # core tests, no display needed
ruff check . && ruff format .
```

The real library lives at `buska-game/library/`, one level **above** the repo. Never create, move, or reference content inside the repo except under `testlib/`.

## Non-negotiables

1. **`core/` never imports Qt.** Game logic, library handling, and importing stay pure Python and unit-tested. UI code depends on `core/`, never the reverse.
2. **No network calls. None.** No telemetry, no crash reporting, no remote images, no update checks, no fonts from a CDN.
3. **Nothing punishes the child.** No score, no timer she can see, no failure state, no harsh sound, no element that disappears as a penalty. A wrong click gets a soft wobble and the question again. If a change would make losing possible, it is wrong.
4. **No text in kid mode.** She cannot read. Voice and motion only.
5. **Data loss is the worst bug.** `library.json` writes are atomic with `.bak` rotation. Deletions go to `_trash/`. A corrupt manifest is repaired from disk, never replaced with an empty one.
6. **Relative paths in the manifest**, always. The library folder must survive being copied to another machine.
7. **Never commit content.** The real library lives outside the repo (`buska-game/library/`, a sibling of `toddler-mouse-dev-game/`), so it's never in a position to be committed — never write code that creates or copies content inside the repo. The one exception is `testlib/`, used for development, which must stay in `.gitignore`. This repo is on GitHub; the content is family photos and recordings of a child's parent.
8. **Add a dependency only if `docs/ARCHITECTURE.md` §1 lists it**, or you have a specific reason to propose an addition. Prefer the standard library and Qt built-ins.
9. **Keep it small.** This is a game with one screen and one interaction. Resist abstraction layers, plugin systems, and configurability nobody asked for. If a feature isn't in `SPEC.md`, ask before building it.

## Conventions

- Type hints everywhere in `core/`; dataclasses for models.
- No blocking calls on the UI thread — imports and audio processing go through `QThreadPool`.
- All kid-mode geometry in fractions of the scene rect, never fixed pixels.
- All timing constants in one module, not scattered as magic numbers in animation calls.
- Commit messages: `area: what changed` (`round_builder: prevent same slot twice in a row`).
- Windows is the primary target; keep Linux working, don't hardcode path separators.

## When something is ambiguous

Ask rather than guess, especially about child-facing behaviour. The difference between a nudge and a punishment is a design decision, not an implementation detail — and the person reviewing this code is the one who will watch her play it.