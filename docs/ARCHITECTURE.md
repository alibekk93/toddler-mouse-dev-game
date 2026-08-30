# Architecture

## 1. Stack

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | |
| GUI | **PySide6** (Qt 6, LGPL) | Needs a real widget toolkit for the parent UI (file dialogs, clipboard images, lists, forms) and a real scene graph for the kid UI. pygame would make parent mode miserable. |
| Kid-mode rendering | `QGraphicsView` / `QGraphicsScene` | Free transforms, z-order, `QPropertyAnimation` on items, hit testing. Exactly what animated cards and a sprite cursor need. |
| Parent-mode UI | Plain `QWidget`s | |
| Audio playback | `QSoundEffect` (QtMultimedia) | Low latency, no extra dependency, several sounds at once, ideal for short WAVs. |
| Audio recording | `sounddevice` + `soundfile` + `numpy` | More predictable than `QMediaRecorder` on Windows, gives raw frames for the level meter and silence-trimming. |
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
│   ├── importer.py        # image + audio normalisation (Pillow, soundfile)
│   ├── round_builder.py   # round selection algorithm (SPEC §2.1)
│   ├── settings.py        # settings.json load/save with defaults
│   └── stats.py           # JSONL append + aggregation
├── ui/
│   ├── kid/
│   │   ├── session.py     # round state machine, timers, transitions
│   │   ├── scene.py       # QGraphicsScene: background, cards, cursor
│   │   ├── card.py        # QGraphicsObject: hover/press/celebrate/wobble
│   │   ├── cursor.py      # sprite cursor item + idle animations
│   │   └── effects.py     # confetti, glow, sparkle trail
│   └── parent/
│       ├── main_window.py # nav shell
│       ├── play_page.py
│       ├── images_page.py # grid, drag-drop, paste, staging tray, bulk tag
│       ├── sounds_page.py # record/playback/trim, target-tag picker
│       ├── settings_page.py
│       └── progress_page.py
├── audio/
│   ├── player.py          # QSoundEffect pool, master volume cap, ducking
│   └── recorder.py        # sounddevice stream, level meter, WAV writer
└── assets/
    ├── cursors/           # paw.svg, bee.svg, star.svg
    └── sfx/               # chime.wav, nudge.wav, pop.wav, whoosh.wav
```

**Hard rule: `core/` imports nothing from Qt.** The round builder, library, and validation are pure Python and fully unit-testable without a display. This is what makes the game logic verifiable at all — you cannot write a meaningful test for a toddler's click, but you can absolutely test that the correct answer never lands in the same slot twice running.

## 3. Kid-mode session state machine

States: `IDLE → INTRO → ASKING → WAITING → (RETRY → WAITING)* → CELEBRATING → INTRO(next)`, plus `PAUSED` reachable from anywhere and `FINISHED`.

- One `QTimer` per pending transition, all cancelled on state exit. No sleeping, no blocking, ever.
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
Use `showFullScreen()` on the chosen `QScreen`. Set `Qt.HighDpiScaleFactorRoundingPolicy.PassThrough`. Lay everything out in fractions of the scene rect, never in fixed pixels — the card sizes in `UX.md` §1 are percentages for exactly this reason.

### 4.4 Clipboard images
`QClipboard.mimeData()` may carry `image/png`, a `text/uri-list` of file paths, or an HTML fragment referencing a remote URL. Handle the first two; **ignore remote URLs entirely** rather than fetching them, since this app makes no network calls.

### 4.5 Long imports blocking the UI
Twelve pasted photos going through decode + resize will freeze the parent window. Run `importer` in a `QThreadPool` worker, report progress, keep the UI alive. `core/importer.py` stays pure Python; only the caller is threaded.

### 4.6 Microphone permissions
Windows 11 requires microphone consent for desktop apps. Detect the failure and say so plainly in the recording UI. Never fail silently to a 0-byte WAV.

## 5. Testing

Unit tests (`pytest`, no display needed) for:
- Round builder: correct-answer position never repeats consecutively; distractors never share the target tag; behaviour when content is insufficient; each distractor strategy.
- Library: atomic save, `.bak` rotation, corrupt-manifest recovery, missing-file detection, duplicate-hash merge.
- Importer: EXIF orientation and stripping, downscale bounds, audio trim/normalise, oversized-file rejection.
- Settings: unknown-key preservation, missing-key defaults.

Manual checklist for kid mode (a human has to look at it):
`hover reaction is instant` · `wrong click feels gentle, not punishing` · `question is audible over a running dishwasher` · `Esc hold ring is visible` · `Alt+Tab pauses` · `nothing on screen invites a click except the cards`.

## 6. Performance targets

- 60fps sustained in kid mode with n=6 and confetti running.
- Round build + card display under 200ms.
- Question audio begins within 300ms of the cards appearing.
- Cold start to parent window under 2s with a 500-image library (thumbnails load lazily).