# Functional Specification

## 1. Modes

The app has a parent window and a kid window, and they never share a screen. Kid mode runs one of two **activities**, chosen by the grown-up before it starts:

- **Quiz** — the question game. This is the product (§2).
- **Warm-up** — pure cursor play, no questions, no right answer (§3).

| | Kid mode | Parent mode |
| --- | --- | --- |
| Window | Fullscreen, frameless, always on top | Normal resizable window |
| Cursor | Custom giant animated sprite | Normal system cursor |
| Text | None (except optional tag caption, off by default) | Ordinary UI |
| Exit | Hold `Esc` for 3 seconds, or `Ctrl+Shift+P` | Close window |

**Startup goes to parent mode**, not kid mode. A grown-up starts an activity deliberately by pressing **Play** or **Warm-up**.

An activity never switches to the other on its own. Warm-up does not "graduate" into a quiz after a while, and the quiz never drops into warm-up when she struggles. The grown-up sitting next to her decides which one she's doing, and the software does not override that.

**Kid mode must be hard to leave by accident and easy to leave on purpose.** A 2-year-old mashes keys. Requirements:

- `Alt+F4`, `Alt+Tab`, `Windows` key: cannot be blocked reliably and we do not try. If the app loses focus, it pauses (audio stops, cards freeze) and shows a "tap to continue" state — it never keeps playing to an empty room.
- Every other key press is swallowed and does nothing.
- The 3-second `Esc` hold shows a growing ring so the parent can see it working; a tap of `Esc` does nothing at all.
- No visible close button, no menu bar, no window chrome.
- **The session is hardened against the machine itself** (see §7). The display must not sleep, the cursor must not escape the window, and Windows accessibility shortcuts must not fire. Each of these otherwise ends a play session outright.

## 2. The round

A **round** is one question. This is the whole game.

```
                 ┌─ repeat clock: replay every `repeat_interval` (§2.2)
                 │
 build round ─→ play question audio ─→ show cards ─→ wait for click
                                                          │
                        ┌─────────────────────────────────┤
                        ▼                                 ▼
                     correct                            wrong
                        │                                 │
              celebrate + praise audio           nudge + replay question
                        │                                 │
                        ▼                                 └──→ back to waiting
                   next round
```

### 2.1 Building a round

Input: the library, the settings, and the previous round.

1. Pick a **prompt** (a recording with a `target_tag`) from the enabled pool. Weighted so recently used prompts are less likely; never the same prompt twice in a row. Where a tag has several recordings, they rotate: if `cat` has "where's the cat?", "can you find the cat?" and "show me the cat", she hears a different one each time the tag comes up. This is why the parent UI pushes for more than one recording per tag (§4.3) — a single clip risks her learning to recognise two seconds of audio rather than the word inside it.
2. Pick the **correct image**: a random enabled image carrying `target_tag`. If several exist, prefer one not shown recently — variety matters, since she should learn "cat" the concept, not one specific cat picture.
3. Pick **n − 1 distractors**: enabled images that do **not** carry `target_tag`, and that do not carry any tag the correct image carries. (Prevents a "dog" distractor when the question is "where is the animal?".)
4. **Shuffle positions.** Constraint: the correct answer must not land in the same slot index as the previous round. Otherwise she learns "always the left one" instead of learning the word.
5. If step 2 or 3 cannot be satisfied, skip this prompt and try another; if nothing works, end the session with the "not enough content" screen (see §6).

Distractor strategy is a setting:

- `mixed` (default) — any non-matching image. Easiest.
- `same_category` — distractors share the correct image's category (all animals, all colours). Harder, better once she's fluent.
- `contrast` — distractors deliberately from other categories. Easiest of all; good for day one.

### 2.2 Waiting

- All n cards are clickable the entire time. There is no lock-out, no "your turn" gating.
- Hovering any card makes it react (see `UX.md` §2). This is the mouse lesson and it runs constantly.
- A **repeat clock** ticks every `repeat_interval` seconds (default 8s) while she hasn't clicked. On each tick:
  - if `repeat_question` is on, replay the question audio;
  - if the tick count has passed `hint_after`, escalate the visual hint.
- The clock resets to zero on any click, right or wrong, and pauses while audio is playing — a repeat never talks over the tail of the previous one.
- Turning `repeat_question` off silences the repeats entirely. The clock still ticks, because hint escalation rides on it: a child who's stuck gets visual help even in a quiet room. Set `hint_after` to `off` as well and the round simply waits, in silence, for as long as it takes.
- **Hinting** means the correct card breathes — a slow scale pulse and a soft glow — growing stronger with each further tick. It never becomes an auto-solve; she still has to click it.

### 2.3 Correct click

1. Cursor sprite does a happy pop.
2. The chosen card scales up and centres; the others gently shrink and fade out.
3. Play, in order: a short chime, then a **praise recording** if the library has any (parent-recorded "yes! that's the cat!" is far better than a chime).
4. Optional confetti/star burst (setting, default on).
5. Pause `celebrate_duration` (default 2.5s), then next round.

### 2.4 Wrong click — the important one

**Never harsh. Never a buzzer. Never a red X. Nothing shrinks, disappears, or is taken away.**

1. The clicked card does a small, soft head-shake wobble (±6°, 400ms, easing out) — the visual of "mm, not that one", not of failure.
2. A gentle low woodblock/marimba note, quieter than the correct chime.
3. Optional parent-recorded retry line ("try again!"), if any exist; picked at random so it doesn't grate.
4. After 600ms, replay the question audio.
5. Everything stays on screen and stays clickable. She can click the same wrong card ten times; it responds the same way ten times.
6. Internally, count the miss for the parent's stats. Nothing on screen reflects it.

## 3. Warm-up activity

A separate activity with no questions, no correct answer, and no library content. Started from its own button in parent mode, never entered automatically.

**Why it exists.** The quiz asks her to learn two things at once: *move my hand and the thing on screen moves with it*, and *this sound means that picture*. The first is a motor skill, the second is language. Warm-up isolates the motor skill so it can be practised on its own, without a wrong answer existing.

**What happens.** Soft shapes — bubbles, stars, simple animals — drift slowly across the screen. They react to the cursor passing over them exactly as cards do in the quiz (scale up, glow, tick sound), and they pop with a pleasing sound and a small burst when clicked. A popped shape is replaced a moment later somewhere else. That is the entire activity.

**Rules:**

- Nothing is ever wrong. There is no target, no instruction, no voice at all beyond the pop sounds.
- Shape count stays between 4 and 8 on screen. Movement is slow: crossing the screen takes 15–25 seconds, so a shape is a target rather than a chase.
- Shapes drift away from each other and never overlap, so a click always has an unambiguous owner.
- Shapes never enter the outer 5% margin of the screen.
- It runs until a grown-up exits, same as the quiz.
- The same cursor, the same hover feedback, the same sound palette. The point is that the skill transfers, so nothing about the interaction may differ from the quiz.

**One setting**, `warmup_shape_count` (default 6, range 4–8). Everything else is fixed.

## 4. Parent mode

Six screens, reachable from a simple left-hand nav.

### 4.1 Play
Two big buttons: **Play** (the quiz) and **Warm-up** (§3). Warm-up needs no content and is therefore always available, including on the very first run before a single picture has been added.

Above them: which categories are enabled, the option count `n`, and a live readiness check ("47 images, 12 questions, ready"). If the library can't build rounds, only the **Play** button is disabled, and the reason is stated plainly ("the tag `truck` has a question but no images").

### 4.2 Images
Grid of thumbnails. Each shows its tags.

Adding images, all three routes must work:
- **File dialog** — multi-select, common formats (PNG, JPG, WEBP, BMP, GIF-first-frame).
- **Drag and drop** onto the grid, including multiple files at once.
- **Clipboard paste** (`Ctrl+V`) — both an image on the clipboard (screenshot, copied web image) and a file path on the clipboard.

On import, every image is normalised (see `ARCHITECTURE.md` §4) and lands in a **staging tray** where the parent types tags before it joins the library. Bulk-tagging: select many, apply a tag to all — essential when you paste twelve dog pictures.

Per-image actions: edit tags, set category, enable/disable, delete, replace.

### 4.3 Sounds
Three lists: **Questions**, **Praise**, **Retry**.

Recording UI (identical for all three):
- One big round record button. Press to start, press to stop. Live input level meter so you can see the mic is working.
- Immediate playback with a waveform; **Keep** / **Re-record** / **Discard**.
- Auto-trim leading and trailing silence, and normalise loudness so no question is much louder than another. This matters — inconsistent volume is unpleasant for the listener sitting close to the speaker.
- For **Questions** only: a required `target_tag` field with autocomplete over existing tags, plus a free-text label so the list is readable ("Where is the cat?").

Also allow importing an existing audio file, for the case where you already have recordings.

**Several recordings per tag are the goal, not an edge case.** The Questions list groups by tag and shows the count for each, with tags having only one recording called out gently ("`cat` — 1 way of asking"). After keeping a recording, offer **Record another way of asking this** as the primary next action rather than closing the dialog. Three phrasings per tag is a good target: "where's the cat?", "can you find the cat?", "show me the cat". The engine rotates them (§2.1), so the more there are, the harder it is for her to pass by recognising a single audio clip.

### 4.4 Settings
| Setting | Default | Range / values |
| --- | --- | --- |
| `option_count` (n) | 2 | 2–6 |
| `distractor_strategy` | `mixed` | `mixed`, `same_category`, `contrast` |
| `enabled_categories` | all | subset |
| `repeat_question` | on | on/off — replay the question while she hasn't clicked |
| `repeat_interval` | 8s | 4–30s — also paces hint escalation |
| `hint_after` | 2 | off, or 0–5 repeat ticks before the correct card starts breathing |
| `celebrate_duration` | 2.5s | 1–5s |
| `cursor_style` | `paw` | sprite name |
| `cursor_scale` | 1.0 | 0.6–2.0 |
| `master_volume` | 0.8 | capped at a safe maximum |
| `confetti` | on | on/off |
| `warmup_shape_count` | 6 | 4–8 (warm-up activity only) |
| `show_tag_caption` | off | on/off (prints the tag under each card — for older siblings) |

Start `option_count` at **2**. Two choices is the right first lesson; the parent raises it when she's bored of winning.

Two things are deliberately *not* settings. Kid mode always opens fullscreen on the primary screen — no windowed mode, no monitor picker. And a session runs until a grown-up exits it — no session timer, no round cap, no "that's enough for today" screen. Knowing when she's had enough is the parent's job, and the software does not second-guess it.

### 4.5 Progress
Two small tables and nothing else.

**Words** — per tag: times asked, first-click accuracy, average time to first click, last seen, and how many recordings it has. A short "she's got these" / "still learning these" split. This tells the parent what to record next.

**Mouse control** — three numbers, aggregated over the last 50 rounds, no time series:

| Number | What it is | What it tells you |
| --- | --- | --- |
| **Path efficiency** | cursor distance travelled ÷ straight-line distance to the card she clicked | How direct her aim is. Falling toward 1.0 means real control. |
| **Overshoots** | average times per round the cursor entered the target card and left again before clicking | Fine control near the target, which is the last thing to develop. |
| **Hover-before-click** | share of clicks preceded by ≥300ms resting on that card | Whether she is aiming or clicking blind. Blind clicking can score well on n=2 and still mean no control at all. |

These are the numbers that tell you when to raise `n`, and accuracy alone will mislead you: a child with no cursor control still scores 50% on two options and 100% once she's guessing well.

No graphs, no history, no streaks, no gamification. Three numbers, a snapshot of now. There is no version of this app where a toddler's performance gets a trend line.

### 4.6 Backup

One button: **Export library**. Writes the entire library folder — manifest, images, audio, settings, stats — to a single timestamped zip (`buska-library-2026-08-30.zip`) at a location the parent picks, defaulting to whatever they chose last time. A matching **Import library** restores one into an empty library folder.

This is not a nice-to-have. The pictures are replaceable; recordings of a parent's voice asking a two-year-old questions are not, and they otherwise exist in exactly one folder on one machine, deliberately outside version control.

- After every 20 additions (images or recordings, cumulative) since the last successful export, show a quiet, dismissible reminder on the Play page. Never a modal, never blocking, never during a session.
- The counter and the last export date live in the app config, not in `library.json` — the manifest describes content, not housekeeping.
- Export must be safe to run with the game open, and must verify the zip after writing rather than reporting success on a truncated file.

## 5. Content model in one paragraph

An **image** is a file plus one or more **tags** plus an optional **category**. A **question** is a recording plus exactly one **target tag**. The game asks a question and treats every image carrying that tag as correct. That is the entire content model, and it is why colours, numbers, letters, logos, and household objects all work without any code change: tag three pictures `red`, record "where is red?", done.

Tags are opaque strings in any language or script — `cat`, `chat`, `кошка`, `7`, `letter_b`, `toyota` are all identical to the engine, which only ever compares them to each other. Nothing anywhere records what language a tag or a recording is in, because nothing needs to.

## 6. Edge cases

| Situation | Behaviour |
| --- | --- |
| Fewer than n usable images for a prompt | Skip that prompt silently; try the next. |
| No prompt can build a round | Kid mode shows a calm "all done" screen (no text — a waving character + a chime) and returns to parent mode after 5s. |
| Image file missing from disk | Manifest entry marked `broken`; excluded from rounds; flagged in parent mode with a **Locate** / **Remove** action. |
| Audio file missing | Same treatment. |
| Window loses focus in kid mode | Pause immediately: stop audio, freeze animations, dim the screen. Resume on a click. |
| No microphone found | Recording UI disabled with a plain explanation; file import still works. |
| Corrupt `library.json` | Do not overwrite it. Load the most recent `library.json.bak`, and if that fails, rebuild from a disk scan. Never start with an empty library on top of a folder full of content. |
| Same image dragged in twice | Detect by content hash, offer to merge tags instead of duplicating. |

## 7. Session hardening

Windows will end a play session on its own if left alone. Three specific defences, all applied on entering kid mode and all released on leaving it — including on crash, via a context manager, since every one of these leaves the machine in an altered state.

| Threat | Defence |
| --- | --- |
| Display sleeps or dims while she studies a card | Keep the display awake for the duration of the session (`SetThreadExecutionState` with `ES_DISPLAY_REQUIRED`). Release it on exit; never leave the machine unable to sleep. |
| Cursor escapes to a screen corner or the taskbar and is lost | Confine the cursor to the game window (`ClipCursor`). Release on focus loss, on pause, and on exit — a clipped cursor with the app frozen is a machine that appears broken. |
| Windows accessibility shortcuts fire | She will hold a key (Filter Keys) and hit Shift five times (Sticky Keys) within a week. Both open a modal dialog over the game. Suppress them for the session and restore the previous settings afterwards. |

Rules:

- Every one of these is a Windows-only `ctypes` call in a single module, wrapped so it is a silent no-op on Linux. Nothing in `core/` or the game logic knows they exist.
- If a defence fails to apply, log it and carry on. Not being able to block Sticky Keys is not a reason to refuse to play.
- Restoration is more important than application. Test the crash path deliberately: kill the process mid-session and confirm the cursor is free and the previous accessibility settings are back.



## 8. Explicit non-goals

Not in v1, and mostly not ever:

- Accounts, cloud sync, sharing libraries, any network traffic.
- Profiles, library switchers, or anything supporting a second child in the UI.
- Text-to-speech. Every question is a parent's recording.
- Session timers, daily limits, or any mechanism that decides she's played enough.
- Windowed mode, monitor pickers, or multi-monitor handling.
- Built-in content packs. The parent's own voice and photos are the point.
- Scores, stars, levels, unlockables, streaks, or any extrinsic reward loop.
- Touchscreen or tablet support.
- Speech recognition, webcam, or any sensor other than mouse and (in parent mode) microphone.
- Ads, analytics, telemetry, crash reporting. Nothing leaves the machine.