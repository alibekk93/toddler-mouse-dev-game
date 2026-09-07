# Kid Mode UX

The rest of the app is ordinary software. This screen is the product.

## 1. Screen anatomy

Fullscreen. One warm, low-saturation background (deep teal / cream, not white — white at fullscreen brightness is harsh at close range). No header, no footer, no logo, no buttons, no text.

Cards are laid out on a fixed grid with generous gaps:

| n | Layout | Card size (of screen height) |
| --- | --- | --- |
| 2 | 1 × 2 | 55% |
| 3 | 1 × 3 | 42% |
| 4 | 2 × 2 | 40% |
| 5 | top 3 / bottom 2, centred | 33% |
| 6 | 2 × 3 | 33% |

Rules that hold at every n:

- **Minimum gap between cards: 8% of screen width.** Her aim is terrible; adjacent targets must not be reachable by a 3px slip.
- **Minimum margin from screen edge: 5%.** Cards never touch the edge, where the cursor gets clamped.
- Cards are rounded squares with a soft shadow and a thick pale border, sitting on the background like physical tiles. The image is letterboxed inside, never cropped — a cat with its head cropped off is not a cat to her.

## 2. The cursor — the actual lesson

This is where most of the implementation effort goes.

**Size.** 96–128 logical px, scaled by `cursor_scale`. Roughly a third the height of a card. Absurd by adult standards; correct here.

**Appearance.** A friendly character, not an arrow: a paw, a bee, a star with a face. High contrast against every background, with a dark outline and a light inner fill so it survives being over a dark photo. The **hotspot is the visual centre**, not the tip — she will aim the middle of the blob at the thing she wants, because that is what it looks like it does.

**Behaviour — the feedback ladder.** Every state must be obvious across the room:

| State | Cursor does | Card does |
| --- | --- | --- |
| Idle, over background | Slow breathing, gentle bob | Nothing |
| Moving fast | Faint trailing sparkles behind it | Nothing |
| Entering a card | Grows ~15%, small "!" perk-up, soft tick sound | Scales to 108%, lifts its shadow, border brightens, tiny wobble |
| Resting on a card | Keeps its enlarged state | Slow glow pulse |
| Mouse button down | Squashes (like being pressed) | Presses down to 96% |
| Button released on card | Springs back with a pop | Resolves per `SPEC.md` §2.3 / §2.4 |
| Leaving a card | Returns to normal size | Settles back to 100% over 200ms |

The hover reaction is the entire mouse lesson: *I move my hand → that thing over there changes → the change follows my hand.* Make it instant (< 1 frame of perceptible lag) and make it big.

**Also handle:**
- **Click-and-hold-then-release-elsewhere.** She will do this constantly. Treat a click as a "select" if the release happens over a card, regardless of where the press started. Be forgiving, not correct.
- **Drag.** Ignore it. No drag interactions exist.
- **Double, triple, sextuple clicks.** Debounce at 400ms; the second click of a rapid burst is discarded, not processed.
- **Right-click and middle-click.** Treated exactly like left-click. She does not know the difference and should not be punished for it.
- **Cursor parked at a screen edge.** The bob animation continues so it never looks dead or frozen.

## 3. Timing

Everything is slower than an adult app, and nothing that matters happens fast.

| Event | Duration |
| --- | --- |
| Cards fade/pop in | 500ms, staggered 120ms apart, left to right |
| Question audio starts | 300ms after the first card appears |
| Card hover scale | 150ms, ease-out-back |
| Wrong-answer wobble | 400ms |
| Delay before question replays after a wrong click | 600ms |
| Correct answer celebration | 2.5s (setting) |
| Cross-fade to next round | 400ms |

**A click cuts the question off.** If the question is still playing when she clicks, stop it and play the response — chime or nudge — immediately. Waiting a second and a half for the sentence to finish before anything acknowledges the click breaks the link between the two, and that link is the thing being taught.

Nothing else is ever cut. Two voices never overlap: the praise or retry line has the channel to itself, and the question only repeats once that line has finished.

## 4. Sound design

- **Correct**: bright ascending three-note chime (major third, then fifth), then the parent's praise recording.
- **Wrong**: a single soft mid-low marimba note. Neutral, not sad, not a buzzer. Distinctly quieter than the correct chime — the loudest thing in the game should always be the good thing.
- **Hover tick**: very quiet, very short. Rate-limited to one per 150ms so sweeping the cursor across all six cards doesn't machine-gun.
- **Card appear**: soft whoosh, one per card, follows the stagger.
- All output passes through a **master volume cap** she cannot change. She will be sitting 40cm from the speakers.

## 5. Attention management

A 2-year-old's attention wanders mid-round. The game's job is to invite her back, never to nag.

- After 15s of no mouse movement at all: the cursor does a bigger, cuter idle animation (a stretch, a yawn, a little hop).
- After 30s of no movement: one extra replay of the question — but only if `repeat_question` is on. When repeats are off they are off, and the game stays quiet rather than finding a loophole to speak through.
- After 3 minutes of no mouse movement or clicks: pause the session, dim to a calm sleep screen. Any mouse movement resumes it.
- If she wanders off entirely, the game waits on the sleep screen indefinitely. It never closes itself, never declares the session over, and never nags her back.

## 6. Warm-up activity

Same cursor, same hover reaction, same sound palette as the quiz (`SPEC.md` §3). Everything below exists so the motor skill she builds here transfers directly.

- **Background** is the quiz background, unchanged. She should recognise the place.
- **Shapes** are simple, high-contrast, and about the size of a quiz card at n=4 (40% of screen height). Bubbles, stars, and simple animal silhouettes, drawn as vectors so they scale cleanly.
- **Movement** is slow drift: 15–25 seconds to cross the screen, direction changing gently, bouncing softly off the 5% margin. Never fast enough to feel like a chase — a target that runs away teaches frustration, not aim.
- **Separation**: shapes repel each other so two never overlap. Every click has one unambiguous owner.
- **Hover** does exactly what a card does: scale to 108%, glow, tick sound.
- **Click** pops the shape — a burst of particles, a bright pluck note, and a replacement fades in elsewhere 1.5s later. Clicking the background does nothing at all, silently.
- **No voice, ever.** The only sounds are the hover tick, the pop, and the fade-in whoosh.
- **No idle nudging** beyond the cursor's own idle animation. There is nothing to be stuck on here.

## 7. Visual accessibility

- **Never rely on colour alone** for any feedback. Every colour change is paired with a scale, motion, or sound change. Colour vision at 2 is fine, but the screen may also be viewed at an angle from a lap.
- Contrast ratio ≥ 4.5:1 for card borders against the background.
- Card images are auto-matted against a light neutral panel so a dark photo and a white-background PNG both read as the same kind of object.
- No flashing above 3Hz anywhere, confetti included.
- Animations respect a `reduced_motion` setting for a child who finds movement overstimulating: keeps the scale changes, drops the trails, sparkles, and confetti.