# Backlog

Known bugs and things to fix, in no particular order. Nothing here is scheduled yet.

This is not `FUTURE_IDEAS.md`. That file holds things deliberately **out** of scope, with
the reasons they were declined. This file holds things that are wrong, or missing, and are
meant to be fixed — they just haven't been.

When one of these lands, delete its entry rather than marking it done, and update the spec
doc it touches in the same commit.

---

## The cursor clip is only released on exit

`SPEC.md` §7 says the `ClipCursor` confinement is released "on focus loss, on pause, and on
exit — a clipped cursor with the app frozen is a machine that appears broken". Only the
exit half exists: `app.py` holds the clip in an `ExitStack` for the whole session and drops
it in `leave_kid`. Alt+Tab away mid-session and the cursor stays confined to the game's
screen while the game is not the thing on top.

Low urgency now that the clip covers the whole primary screen rather than a mis-sized
rectangle — on a single monitor it confines the cursor to where it already was. It bites
on a docked laptop or a projector, where the cursor cannot reach the second display.

The natural place for it is M4's focus-loss pause, which is the machinery that has to know
about the same event. Do it there, not before.

Touches: `app.py`, `ui/kid/window.py`, `platform/windows.py`, `ROADMAP.md` M4.
