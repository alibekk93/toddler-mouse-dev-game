# Architecture

## 1. Stack

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | |
| GUI | **PySide6** (Qt 6, LGPL) | Needs a real widget toolkit for the parent UI (file dialogs, clipboard images, lists, forms) and a real scene graph for the kid UI. pygame would make parent mode miserable. |
| Kid-mode rendering | `QGraphicsView` / `QGraphicsScene` | Free transforms, z-order, `QPropertyAnimation` on items, hit testing. Exactly what animated cards and a sprite cursor need. |
| Parent-mode UI | Plain `QWidget`s | |
| Audio playback | `QSoundEffect` (QtMultimedia) | Low latency, no extra dependency, several sounds at once, ideal for short WAVs. |
| Audio recording | `QAudioSource` (QtMultimedia) | Gives raw PCM frames for the level meter and silence-trimming, with no new dependency. The objection this table used to record was to `QMediaRecorder` — the high-level *encoder* — and it still stands; `QAudioSource` is the low-level half. Chosen at M3 over `sounddevice`+`soundfile`+`numpy`, which cost three dependencies and ~30MB of frozen build for frames we already get. If it proves flaky on Windows, `audio/recorder.py` is the only module to swap. |
| Audio processing | stdlib `wave` + `array` | Trim and peak-normalisation are three passes over an int16 array (`core/importer.py`). Pure Python keeps `core/` Qt-free and numpy-free; ~0.2s for a 10s clip, run on a worker thread. |
| Images | `Pillow` | Import-time normalisation only; Qt handles display. |
| Packaging | PyInstaller, one-dir | |
| Tests | `pytest` for `core/`, manual checklist for UI | |

Deliberately not used: any web view, any game engine, any ORM, any network library. If a dependency isn't in the table above, question whether the feature needs to exist.

## 2. Module layout

Repo root: `buska-game/toddler-mouse-dev-game/`. Package: `toddler_mouse_game/`.

```
toddler_mouse_game/
├── __main__.py            # entry point, CLI args (--library, --kid)
├── app.py                 # QApplication, mode switching, lifecycle
├── core/                  # zero Qt imports below this line
│   ├── models.py          # Image, Sound, Settings dataclasses
│   ├── library.py         # load/save/validate/repair library.json
│   ├── importer.py        # image + audio normalisation (Pillow, stdlib wave)
│   ├── round_builder.py   # round selection algorithm (SPEC §2.1)
│   ├── settings.py        # settings.json load/save with defaults
│   ├── backup.py          # library export/import as zip
│   └── stats.py           # JSONL append + aggregation, motor metrics
├── ui/
│   ├── kid/
│   │   ├── session.py     # quiz state machine, timers, transitions
│   │   ├── warmup.py      # warm-up activity: drifting shapes, popping
│   │   ├── scene.py       # QGraphicsScene: background, cards, cursor
│   │   ├── card.py        # QGraphicsObject: hover/press/celebrate/wobble
│   │   ├── cursor.py      # sprite cursor item + idle animations
│   │   ├── tracker.py     # cursor path metrics for the round (§4.7)
│   │   └── effects.py     # confetti, glow, sparkle trail
│   └── parent/
│       ├── main_window.py # nav shell
│       ├── play_page.py   # Play + Warm-up buttons, readiness, backup reminder
│       ├── images_page.py # grid, drag-drop, paste, staging tray, bulk tag
│       ├── crop_dialog.py # drag a crop rectangle before the picture is written
│       ├── sounds_page.py # record/playback/trim, target-tag picker
│       ├── settings_page.py
│       ├── progress_page.py
│       └── backup_page.py # export/import library zip
├── platform/
│   └── windows.py         # session hardening ctypes calls, no-op elsewhere
├── audio/
│   ├── player.py          # QSoundEffect pool, master volume cap, ducking
│   └── recorder.py        # QAudioSource stream, level meter, WAV writer
└── assets/
    ├── cursors/           # paw.svg, bee.svg, star.svg
    └── sfx/               # chime.wav, nudge.wav, pop.wav, whoosh.wav
```

**Hard rule: `core/` imports nothing from Qt.** The round builder, library, and validation are pure Python and fully unit-testable without a display. This is what makes the game logic verifiable at all — you cannot write a meaningful test for a toddler's click, but you can absolutely test that the correct answer never lands in the same slot twice running.

## 3. Kid-mode session state machine

Quiz states: `IDLE → INTRO → ASKING → WAITING → (RETRY → WAITING)* → CELEBRATING → INTRO(next)`, plus `PAUSED` reachable from anywhere and `FINISHED`.

The warm-up activity (`SPEC.md` §3) has no state machine — it is a single continuous loop of drifting shapes with `PAUSED` and `FINISHED`. It shares `scene.py`, `cursor.py`, and `effects.py` with the quiz and knows nothing about the library. Keep it that way: warm-up must remain runnable on an empty library, which also makes it the fastest way to test cursor behaviour in isolation.

- One `QTimer` per pending transition, all cancelled on state exit. No sleeping, no blocking, ever.
- `WAITING` additionally owns one repeating timer, the repeat clock (`SPEC.md` §2.2), fired every `repeat_interval`. It carries a tick counter that drives both the audio repeat and the hint escalation, resets on every click, and is suspended while any voice audio is playing so repeats never stack. It is the only repeating timer in the app; everything else is one-shot.
- All state lives in `session.py`; `scene.py` only renders and emits input signals. Do not scatter timing logic across card widgets.
- `PAUSED` is entered on focus loss, on the 3-minute idle rule, and on `Esc` hold start. It stops audio and freezes animations, and it must be re-entrant-safe.

## 4. Known traps

These are the things that will actually cost time. Address them early.

### 4.1 The giant cursor
Two approaches, and the choice matters:

- **Hardware cursor** — `QCursor(QPixmap)`. Perfectly smooth, zero lag, but Windows practically caps custom cursors around 128px and animating it means swapping pixmaps, which is coarse.
- **Drawn sprite** — hide the real cursor with `Qt.BlankCursor`, draw a `QGraphicsItem` at the mouse position. Fully animatable, any size, but it lags the physical mouse by a frame or more, which reads as "sluggish" and undermines the exact hand-to-screen link we're teaching.

**Build the drawn sprite** (the animation is worth it), but: enable `setMouseTracking(True)`, update the item position directly in `mouseMoveEvent` rather than on a timer tick, and keep the scene cheap enough to hold 60fps. Add a `cursor_mode: sprite|hardware` setting so it can be flipped if the sprite feels laggy on the target machine. Test on the actual computer she'll use, early.

### 4.2 Audio latency and overlap
`QSoundEffect` needs its WAVs pre-loaded and kept alive — instances garbage-collected mid-playback fail silently, which is a classic and baffling Qt bug to chase. Keep a persistent pool. Pre-load the current round's question and all sfx during the previous round's celebration. Duck sfx under voice rather than stopping it.

### 4.3 Fullscreen and DPI
Use `showFullScreen()` on the primary `QScreen` — single monitor is a fixed constraint, so no screen selection logic. Set `Qt.HighDpiScaleFactorRoundingPolicy.PassThrough`. Lay everything out in fractions of the scene rect, never in fixed pixels — the card sizes in `UX.md` §1 are percentages for exactly this reason.

### 4.4 Clipboard images
`QClipboard.mimeData()` may carry `image/png`, a `text/uri-list` of file paths, or an HTML fragment referencing a remote URL. Handle the first two; **ignore remote URLs entirely** rather than fetching them, since this app makes no network calls.

### 4.5 Long imports blocking the UI
Twelve pasted photos going through decode + resize will freeze the parent window. Run `importer` in a `QThreadPool` worker, report progress, keep the UI alive. `core/importer.py` stays pure Python; only the caller is threaded.

### 4.6 Microphone permissions
Windows 11 requires microphone consent for desktop apps. Detect the failure and say so plainly in the recording UI. Never fail silently to a 0-byte WAV.

### 4.7 Cursor path tracking
The motor metrics on the Progress page (`SPEC.md` §4.5) need the distance the cursor actually travelled during a round. Accumulate it in the same `mouseMoveEvent` that moves the sprite — sum the segment lengths, count target entries and exits, and note whether the cursor rested on the clicked card for ≥300ms before the click. Four scalars per round, no path history retained. Do not sample on a timer: a timer both misses fast movement and inflates the total when the mouse is still.

### 4.8 Session hardening lifecycle
`SPEC.md` §7 calls for `SetThreadExecutionState`, `ClipCursor`, and suppressing Sticky/Filter Keys. All three live in `platform/windows.py`, behind one context manager entered on kid-mode start and exited on stop. Two rules: it must no-op cleanly on non-Windows, and restoration must survive a crash — install an `atexit` hook and an exception handler, then test by killing the process mid-session. A machine left with a clipped cursor and Sticky Keys disabled is a worse bug than anything in the game.

## 5. Testing

Unit tests (`pytest`, no display needed) for:
- Round builder: correct-answer position never repeats consecutively; distractors never share the target tag; behaviour when content is insufficient; each distractor strategy.
- Library: atomic save, `.bak` rotation, corrupt-manifest recovery, missing-file detection, duplicate-hash merge.
- Importer: EXIF orientation and stripping, downscale bounds, audio trim/normalise, oversized-file rejection.
- Settings: unknown-key preservation, missing-key defaults.
- Backup: export produces a zip that imports into an empty folder and yields an identical manifest; verification catches a truncated file.
- Stats: motor metric aggregation over a synthetic round log — path efficiency, overshoot count, hover-before-click share.
- Tag handling: casefold and NFC normalisation on Cyrillic and accented Latin tags, round-trip through `library.json` with `ensure_ascii=False`, matching a Russian tag against a question recorded for it.

Manual checklist for kid mode (a human has to look at it):
`hover reaction is instant` · `wrong click feels gentle, not punishing` · `question is audible over a running dishwasher` · `repeats never talk over each other` · `repeats off means genuinely silent` · `Esc hold ring is visible` · `Alt+Tab pauses` · `display never sleeps mid-session` · `cursor cannot leave the window` · `five Shift presses do nothing` · `all three released after a forced kill` · `a click during the question cuts it and answers immediately` · `nothing on screen invites a click except the cards`.

## 6. Performance targets

- 60fps sustained in kid mode with n=6 and confetti running.
- Round build + card display under 200ms.
- Question audio begins within 300ms of the cards appearing.
- Cold start to parent window under 2s with a 500-image library (thumbnails load lazily).