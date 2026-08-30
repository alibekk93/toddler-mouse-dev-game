# Where Is It?

A tiny, offline, parent-authored pointing game that teaches a 2-year-old to use a computer mouse.

A recorded voice asks **"Where is the cat?"**. Two to six pictures appear. She moves a big friendly cursor across the screen, watches the pictures wake up as the cursor passes over them, and clicks the cat. Something nice happens. Next question.

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
│       └── ROADMAP.md             ← milestones, in build order
└── library/                       ← the real content: her pictures and your voice
```

**The real library sits beside the repo, never inside it.** It holds family photos and recordings of your voice; it has no business in a git history, public or private. Run the game with `--library ../library` and the separation stays automatic. `testlib/` inside the repo is for junk test images only, and is gitignored anyway.

Point the Claude Code session at `toddler-mouse-dev-game/`, not at `buska-game/`. `CLAUDE.md` at the repo root is what gets picked up automatically.

Read order for a fresh Claude Code session: `CLAUDE.md` → `docs/ROADMAP.md` → `docs/SPEC.md` → whichever of `docs/UX.md` / `docs/DATA_MODEL.md` / `docs/ARCHITECTURE.md` the current milestone touches.

## Assumptions I made

Correct any of these before building and the docs will need small edits:

- **Fullscreen, single monitor, mouse only.** No touch, no gamepad, no tablet mode. Touch input would undercut the entire point.
- **One child, one library.** No user accounts, no profiles. If a second child needs a separate library, that is a folder swap, not a feature.
- **Question audio is recorded, not synthesised.** Text-to-speech exists only as an optional fallback for tags with no recording, off by default.
- **Rounds run forever** until a grown-up exits. There is an optional session limit in settings, off by default.
- **English/French tag names**, but nothing in the code cares — tags are opaque strings, and the audio is whatever language you record in.