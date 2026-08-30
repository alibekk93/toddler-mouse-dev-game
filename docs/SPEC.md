# Functional Specification

## 1. Modes

The app has exactly two modes and they never share a window.

| | Kid mode | Parent mode |
| --- | --- | --- |
| Window | Fullscreen, frameless, always on top | Normal resizable window |
| Cursor | Custom giant animated sprite | Normal system cursor |
| Text | None (except optional tag caption, off by default) | Ordinary UI |
| Exit | Hold `Esc` for 3 seconds, or `Ctrl+Shift+P` | Close window |

**Startup goes to parent mode**, not kid mode. A grown-up starts a session deliberately by pressing **Play**.

**Kid mode must be hard to leave by accident and easy to leave on purpose.** A 2-year-old mashes keys. Requirements:

- `Alt+F4`, `Alt+Tab`, `Windows` key: cannot be blocked reliably and we do not try. If the app loses focus, it pauses (audio stops, cards freeze) and shows a "tap to continue" state — it never keeps playing to an empty room.
- Every other key press is swallowed and does nothing.
- The 3-second `Esc` hold shows a growing ring so the parent can see it working; a tap of `Esc` does nothing at all.
- No visible close button, no menu bar, no window chrome.

## 2. The round

A **round** is one question. This is the whole game.

```
                 ┌─ replay after HINT_DELAY, up to REPLAY_LIMIT times
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

1. Pick a **prompt** (a recording with a `target_tag`) from the enabled pool. Weighted so recently used prompts are less likely; never the same prompt twice in a row.
2. Pick the **correct image**: a random enabled image carrying `target_tag`. If several exist, prefer one not shown recently — variety matters, since she should learn "cat" the concept, not one specific cat picture.
3. Pick **n − 1 distractors**: enabled images that do **not** carry `target_tag`, and that do not carry any tag the correct image carries. (Prevents a "dog" distractor when the question is "where is the animal?".)
4. **Shuffle positions.** Constraint: the correct answer must not land in the same slot index as the previous round. Otherwise she learns "always the left one" instead of learning the word.
5. If step 2 or 3 cannot be satisfied, skip this prompt and try another; if nothing works, end the session with the "not enough content" screen (see §5).

Distractor strategy is a setting:

- `mixed` (default) — any non-matching image. Easiest.
- `same_category` — distractors share the correct image's category (all animals, all colours). Harder, better once she's fluent.
- `contrast` — distractors deliberately from other categories. Easiest of all; good for day one.

### 2.2 Waiting

- All n cards are clickable the entire time. There is no lock-out, no "your turn" gating.
- Hovering any card makes it react (see `UX.md` §2). This is the mouse lesson and it runs constantly.
- After `hint_delay` seconds of no click (default 8s), replay the question audio.
- After `replay_limit` replays (default 2), start **hinting**: the correct card breathes — a slow scale pulse and a soft glow — increasing in strength every further `hint_delay`. It never becomes an auto-solve; she still has to click it.

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

## 3. Parent mode

Five screens, reachable from a simple left-hand nav.

### 3.1 Play
Big **Play** button. Above it: which decks/categories are enabled, the option count `n`, and a live readiness check ("47 images, 12 questions, ready"). If the library can't build rounds, the button is disabled and the reason is stated plainly ("the tag `truck` has a question but no images").

### 3.2 Images
Grid of thumbnails. Each shows its tags.

Adding images, all three routes must work:
- **File dialog** — multi-select, common formats (PNG, JPG, WEBP, BMP, GIF-first-frame).
- **Drag and drop** onto the grid, including multiple files at once.
- **Clipboard paste** (`Ctrl+V`) — both an image on the clipboard (screenshot, copied web image) and a file path on the clipboard.

On import, every image is normalised (see `ARCHITECTURE.md` §4) and lands in a **staging tray** where the parent types tags before it joins the library. Bulk-tagging: select many, apply a tag to all — essential when you paste twelve dog pictures.

Per-image actions: edit tags, set category, enable/disable, delete, replace.

### 3.3 Sounds
Three lists: **Questions**, **Praise**, **Retry**.

Recording UI (identical for all three):
- One big round record button. Press to start, press to stop. Live input level meter so you can see the mic is working.
- Immediate playback with a waveform; **Keep** / **Re-record** / **Discard**.
- Auto-trim leading and trailing silence, and normalise loudness so no question is much louder than another. This matters — inconsistent volume is unpleasant for the listener sitting close to the speaker.
- For **Questions** only: a required `target_tag` field with autocomplete over existing tags, plus a free-text label so the list is readable ("Where is the cat?").

Also allow importing an existing audio file, for the case where you already have recordings.

### 3.4 Settings
| Setting | Default | Range / values |
| --- | --- | --- |
| `option_count` (n) | 2 | 2–6 |
| `distractor_strategy` | `mixed` | `mixed`, `same_category`, `contrast` |
| `enabled_categories` | all | subset |
| `hint_delay` | 8s | 4–20s |
| `replay_limit` | 2 | 0–5 |
| `celebrate_duration` | 2.5s | 1–5s |
| `cursor_style` | `paw` | sprite name |
| `cursor_scale` | 1.0 | 0.6–2.0 |
| `master_volume` | 0.8 | capped at a safe maximum |
| `confetti` | on | on/off |
| `show_tag_caption` | off | on/off (prints the tag under each card — for older siblings) |
| `session_limit` | off | off, or 5–30 minutes |
| `monitor` | primary | monitor picker |

Start `option_count` at **2**. Two choices is the right first lesson; the parent raises it when she's bored of winning.

### 3.5 Progress
Deliberately modest. Per tag: times asked, first-click accuracy, average time to first click, last seen. A short "she's got these" / "still learning these" split. No graphs of a toddler's performance over time, no streaks, no gamification. It exists so the parent knows what to record next.

## 4. Content model in one paragraph

An **image** is a file plus one or more **tags** plus an optional **category**. A **question** is a recording plus exactly one **target tag**. The game asks a question and treats every image carrying that tag as correct. That is the entire content model, and it is why colours, numbers, letters, logos, and household objects all work without any code change: tag three pictures `red`, record "where is red?", done.

## 5. Edge cases

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

## 6. Explicit non-goals

Not in v1, and mostly not ever:

- Accounts, cloud sync, sharing libraries, any network traffic.
- Built-in content packs. The parent's own voice and photos are the point.
- Scores, stars, levels, unlockables, streaks, or any extrinsic reward loop.
- Touchscreen or tablet support.
- Speech recognition, webcam, or any sensor other than mouse and (in parent mode) microphone.
- Ads, analytics, telemetry, crash reporting. Nothing leaves the machine.