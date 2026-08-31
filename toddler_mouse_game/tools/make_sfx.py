"""Generate the placeholder sound effects.

These are stand-ins so M2 has something to play. Real sound design is M4 — when you
replace these, keep the shape described in UX §4 and keep the loudness relationship:
**the loudest thing in the game is always the good thing.**

    python -m toddler_mouse_game.tools.make_sfx
"""

import math
import struct
import sys
import wave
from pathlib import Path

RATE = 48_000
OUT = Path(__file__).resolve().parent.parent / "assets" / "sfx"


def _write(name: str, samples: list[float]) -> Path:
    peak = max(abs(s) for s in samples) or 1.0
    frames = b"".join(struct.pack("<h", int(32_000 * s / peak)) for s in samples)
    path = OUT / name
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return path


def _note(frequency: float, ms: int, decay: float = 6.0, harmonic: float = 0.3) -> list[float]:
    """A struck-bar sort of note: fundamental plus a quiet octave, decaying fast."""
    total = int(RATE * ms / 1000)
    out = []
    for n in range(total):
        t = n / RATE
        envelope = math.exp(-decay * t) * min(1.0, n / 240)  # short attack, no click
        body = math.sin(2 * math.pi * frequency * t)
        body += harmonic * math.sin(4 * math.pi * frequency * t)
        out.append(envelope * body)
    return out


def _mix(layers: list[tuple[int, list[float]]]) -> list[float]:
    length = max(offset + len(data) for offset, data in layers)
    out = [0.0] * length
    for offset, data in layers:
        for i, value in enumerate(data):
            out[offset + i] += value
    return out


def _scaled(samples: list[float], gain: float) -> list[float]:
    return [s * gain for s in samples]


def build() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []

    # Correct: a bright ascending three-note chime — root, major third, fifth (UX §4).
    step = int(RATE * 0.11)
    written.append(
        _write(
            "chime.wav",
            _mix(
                [
                    (0, _note(523.25, 700)),  # C5
                    (step, _note(659.25, 700)),  # E5
                    (2 * step, _note(783.99, 900)),  # G5
                ]
            ),
        )
    )

    # Wrong: one soft mid-low note. Neutral, not sad, not a buzzer — and distinctly
    # quieter than the chime, since nothing punishing should be the loudest sound.
    written.append(_write("nudge.wav", _scaled(_note(233.08, 520, decay=8.0, harmonic=0.15), 0.45)))

    # Warm-up pop: a bright short pluck.
    written.append(_write("pop.wav", _scaled(_note(880.0, 260, decay=18.0, harmonic=0.5), 0.8)))

    # Hover tick: very quiet, very short.
    written.append(_write("tick.wav", _scaled(_note(1320.0, 60, decay=45.0, harmonic=0.0), 0.22)))

    # Card appear: a soft filtered-noise whoosh, one per card.
    total = int(RATE * 0.32)
    noise, previous, seed = [], 0.0, 12345
    for n in range(total):
        seed = (1103515245 * seed + 12345) % (2**31)
        white = (seed / 2**30) - 1.0
        previous = previous * 0.86 + white * 0.14  # crude low-pass
        envelope = math.sin(math.pi * n / total) ** 2
        noise.append(previous * envelope)
    written.append(_write("whoosh.wav", _scaled(noise, 0.5)))

    return written


if __name__ == "__main__":
    for path in build():
        print(f"{path.name:12} {path.stat().st_size:>7,} bytes")
    sys.exit(0)
