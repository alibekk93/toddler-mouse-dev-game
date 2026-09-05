# Where Is It?

A tiny, offline, parent-authored pointing game that teaches a 2-year-old to use a computer mouse.

A recorded voice asks **"Where is the cat?"**. Two to six pictures appear. She moves a big friendly cursor across the screen, watches the pictures wake up as the cursor passes over them, and clicks the cat. Something nice happens. Next question.

Alongside it there's a **warm-up** activity: no questions, no right answer, just slow-drifting shapes that pop when she clicks them. Pointing at things is a motor skill and naming things is language; warm-up lets her practise the first without the second, which matters a lot in the first few weeks.

The content is entirely yours: you record the questions in your own voice and add the pictures yourself. Animals today, colours tomorrow, car logos the week after. The game itself knows nothing about cats — it only knows about **images with tags** and **recordings that ask for a tag**.

---

## Why this design

Everything in this spec follows from three facts about the player:

1. **She cannot read.** No text is load-bearing anywhere in kid mode. Every instruction is voice; every response is motion and sound.
2. **She has never used a pointing device.** The cursor is not a UI detail here — it is the thing being taught. It is huge, animated, and every object on screen reacts to it. Hover feedback is the lesson.
3. **She cannot fail.** There is no score, no timer, no losing, no "wrong" sound that startles. A wrong click gets a soft nudge and the question again, forever, until she gets it. The only outcome is success, arriving later or sooner.

## Chosen stack

| Decision | Choice |
| --- | --- |
| Runtime | Python 3.11+ desktop app, **PySide6** |
| Content storage | Plain folder of files + `library.json` manifest |
| Wrong answer | Gentle nudge, replay question, keep going |
| Network | None. The app never makes a network call. |
| Primary OS | Windows (dev + play), Linux kept working |

## Where things live

```
buska-game/                        ← wrapper folder, NOT under version control
├── toddler-mouse-dev-game/        ← the git repo: code + docs only
│   ├── README.md                  ← this file
│   ├── CLAUDE.md                  ← instructions for the Claude Code session
│   ├── pyproject.toml
│   ├── toddler_mouse_game/        ← the Python package
│   ├── tests/
│   ├── testlib/                   ← throwaway test content, gitignored
│   └── docs/
│       ├── SPEC.md                ← functional spec: modes, game loop, parent tools
│       ├── UX.md                  ← kid-mode interaction design: cursor, timing, feedback
│       ├── DATA_MODEL.md          ← folder layout, JSON schemas, validation
│       ├── ARCHITECTURE.md        ← modules, libraries, threading, known traps
│       ├── ROADMAP.md             ← milestones, in build order
│       ├── BACKLOG.md             ← known bugs and gaps, meant to be fixed
│       └── FUTURE_IDEAS.md        ← deliberately out of scope, with reasons
└── library/                       ← the real content: her pictures and your voice
```

**The real library sits beside the repo, never inside it.** It holds family photos and recordings of your voice; it has no business in a git history, public or private. Run the game with `--library ../library` and the separation stays automatic. `testlib/` inside the repo is for junk test images only, and is gitignored anyway.

Point the Claude Code session at `toddler-mouse-dev-game/`, not at `buska-game/`. `CLAUDE.md` at the repo root is what gets picked up automatically.

Read order for a fresh Claude Code session: `CLAUDE.md` → `docs/ROADMAP.md` → `docs/SPEC.md` → whichever of `docs/UX.md` / `docs/DATA_MODEL.md` / `docs/ARCHITECTURE.md` the current milestone touches.

## Running it

Python 3.11+, from the repo root:

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev]"

python -m toddler_mouse_game.tools.seed --library ./testlib --demo   # throwaway content
python -m toddler_mouse_game --library ./testlib                     # start here
```

Day to day it's `--library ../library`, the real folder beside the repo. `pytest` runs the
core tests with no display; `ruff check . && ruff format .` before committing.

The app opens in parent mode. **Warm-up** plays on a completely empty library; **Play** is
disabled until there are pictures and a question for one of them, and says which is
missing. Add pictures on the **Pictures** page — file dialog, drag and drop, or `Ctrl+V` —
type their tags in the tray at the bottom, then record the questions on the **Sounds**
page. Hold `Esc` for 3 seconds to leave kid mode.

Built so far: M0–M3 of `docs/ROADMAP.md`. Still to come are the polish pass (M4) and the
Settings, Progress, and Backup pages (M5), so the nav has three entries rather than six.
Recording needs a microphone — without one the record button is disabled and explains
itself, and importing a `.wav` still works.

## Fixed constraints

These are settled, not open questions. Build against them.

- **Fullscreen, single monitor, mouse only.** No touch, no gamepad, no tablet mode, no monitor picker. Touch input would undercut the entire point.
- **One child, one library.** No accounts, no profiles, no library switcher in the UI. A second library, if it ever happens, is a `--library` flag and a folder swap — not a feature.
- **Question audio is always recorded by a parent.** No text-to-speech anywhere in the app.
- **The two activities never switch on their own.** A grown-up picks quiz or warm-up before the session starts.
- **Rounds run forever** until a grown-up exits. No session timer, no daily limit, no "that's enough for today" screen. Knowing when to stop is the parent's job, not the software's.
- **Tags are opaque strings in any language or script.** English, French, Russian, mixed — the engine never reads them, and nothing in the code or the data model records what language anything is in. The audio is simply whatever you recorded.