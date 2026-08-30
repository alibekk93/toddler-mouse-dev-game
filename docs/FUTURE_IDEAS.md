# Future Ideas

Things deliberately **not** in v1. Nothing here should be built without a decision to move it into `ROADMAP.md` first — and most of it should only be built after months of watching her actually play.

The ordering rule: v1 is a game where a parent's voice asks for a picture and a toddler clicks it. Anything that makes that loop more complicated to build, or more complicated to explain, waits.

---

## Weighted prompt selection

**The idea.** Replace uniform-random prompt choice with a scheduler that biases toward tags she is close to knowing, keeps one or two genuinely new tags in rotation, and lets mastered tags reappear occasionally rather than never. Roughly: sort tags into *new*, *learning*, and *known* by first-click accuracy over the last N attempts, then draw with weights around 20/60/20.

**Why it's tempting.** With 40 tags and uniform random selection, each one comes up about once every 40 rounds — too sparse to consolidate anything. The stats log already carries everything a scheduler would need, so the data side is free.

**Why it's not in v1.** It is the one part of this project that can be subtly wrong for weeks without anyone noticing. Tuning a spaced-repetition curve for a two-year-old is guesswork; getting it wrong means she either grinds the same four tags or never revisits anything. Uniform random is legible: if she's seeing too much of something, you can see why immediately, and the parent can fix it by disabling a category. Ship the legible version, watch what actually happens, and only then decide what the weighting should be.

**When to revisit.** After there are a few weeks of real stats in `stats/*.jsonl` — enough to look at whether accuracy per tag actually moves over time, which is the assumption the whole idea rests on.

---

## Sequence mode

"Find the cat, then the dog." Two-step working memory rather than single-step recognition. A natural sequel once single questions are easy, and a genuinely different skill.

## Difficulty drift

Auto-raise `n` for tags with consistently high first-click accuracy, and drop it back when she struggles. Depends on the motor metrics being trustworthy first — accuracy alone is not enough to justify making the game harder.

## Click-and-drag mode

Drag the cat into the basket. A significantly harder motor skill than clicking, and the obvious next thing to teach once pointing and clicking are solved.

---

## Suggested and declined

Recorded so they don't get re-proposed and re-declined every few months:

- **Invisible hit padding around cards** — enlarging the clickable area beyond the drawn card. Declined for now; revisit if near-misses turn out to be common in real play.
- **Folder-name auto-tagging on import** (`animals/cat/*.jpg` → tags `cat`, `animals`). Declined; manual tagging is fine at the library sizes expected.
- **Guided add flow** — prompting to record a question immediately after tagging a new image.
- **Subject isolation on import** — background removal so a cat on a busy sofa reads as cleanly as a cat on white. Declined mainly on dependency weight.