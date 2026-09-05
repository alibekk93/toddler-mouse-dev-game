# Backlog

Known bugs and things to fix, in no particular order. Nothing here is scheduled yet.

This is not `FUTURE_IDEAS.md`. That file holds things deliberately **out** of scope, with
the reasons they were declined. This file holds things that are wrong, or missing, and are
meant to be fixed — they just haven't been.

When one of these lands, delete its entry rather than marking it done, and update the spec
doc it touches in the same commit.

---

## Distractors can be accidentally correct

A question asking `yellow` picks its distractors from images that share no tag with the
correct answer (`core/round_builder.py`, `_distractor_pool`). A photo of a yellow-ish dog
tagged only `dog` shares nothing with a yellow square tagged `yellow`, so it is a perfectly
valid distractor — and it is also, to a two-year-old looking at it, yellow. She clicks the
dog, she is right, and the game tells her she is wrong.

The engine cannot see this: it compares tags, and nothing records that the dog picture
*happens to be* yellow. Some ideas, none decided:

- Make the round's category a hard constraint rather than the `same_category` *preference*
  it is today — a colour question draws only from images in the `colours` category, so
  every option on screen is a colour swatch and the comparison is honest.
- Or an explicit per-image "never a distractor for these tags" exclusion list, typed by a
  parent when they notice the clash.

The first is cheaper and needs no new manifest field, but it only works once an image can
be in more than one category (below) — a yellow square is both a colour and a shape.

Touches: `core/round_builder.py`, `SPEC.md` §2.1.

## An image can only have one category

`Image.category` is a single optional string (`core/models.py`, `DATA_MODEL.md` §3). It
should be a list: a yellow square is a colour *and* a shape, a photo of the family cat is
an animal *and* a person's pet. The single field forces a false choice at tagging time, and
it is what makes the distractor fix above awkward.

Needs a manifest migration (string → list, tolerating the old form on load), the
`enabled_categories` setting to match, and the category field on the Pictures page to
accept several.

Touches: `core/models.py`, `core/library.py`, `core/round_builder.py`,
`ui/parent/images_page.py`, `DATA_MODEL.md` §3, `SPEC.md` §4.4.

## No way to crop an image when adding it

Import normalises and downscales but never crops (`core/importer.py`, `DATA_MODEL.md` §8).
A photo where the cat is a small part of a busy kitchen is a bad card: the picture is
letterboxed into the card whole, so the subject ends up tiny. A parent should be able to
drag a crop rectangle in the staging tray before the picture joins the library, and the
cropped version is what gets saved and hashed.

Note that cropping changes the normalised bytes, so it must happen *before* the id is
allocated — a crop applied afterwards is a different picture, not an edit of one.

Touches: `core/importer.py`, `ui/parent/images_page.py`, `DATA_MODEL.md` §8.

## A click during the question waits for the audio to finish

Right now a click that lands while the question is still playing resolves the round, but
the response sound is queued until the question audio finishes
(`audio/player.py`, `after_voice`). It should instead stop the question immediately and
play the outcome — chime or nudge — straight away. Waiting a second and a half for a
sentence to finish before anything acknowledges her click breaks the link between the click
and the result, which is the thing being taught.

**This reverses a stated rule.** `UX.md` §3 currently says "Never cut audio off. If the
question is still playing when she clicks, let the click resolve but let the audio finish,
then play the response sound." Fixing this means changing that line too, deliberately, not
quietly working around it.

Touches: `audio/player.py`, `ui/kid/session.py`, `UX.md` §3.
