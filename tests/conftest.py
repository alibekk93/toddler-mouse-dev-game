"""Shared helpers for building throwaway media in tests."""

import math
import struct
import wave

from PIL import Image as PILImage


def make_image(path, size=(400, 300), colour=(200, 60, 60), mode="RGB", **save_kwargs):
    image = PILImage.new(mode, size, colour)
    image.save(path, **save_kwargs)
    return path


def _pack(value, width):
    """One int16 sample as `width` bytes of little-endian PCM, the way a WAV stores it."""
    if width == 1:  # 8-bit WAV is unsigned
        return struct.pack("<B", (value >> 8) + 128)
    if width == 2:
        return struct.pack("<h", value)
    return (value << (8 * (width - 2))).to_bytes(width, "little", signed=True)


def make_wav(
    path,
    ms=250,
    rate=48_000,
    frequency=440.0,
    amplitude=12_000,
    silence_ms=0,
    channels=1,
    width=2,
):
    """A test tone. `silence_ms` pads both ends, for the trim tests."""
    lead = [0] * int(rate * silence_ms / 1000)
    tone = [
        int(amplitude * math.sin(2 * math.pi * frequency * n / rate))
        for n in range(int(rate * ms / 1000))
    ]
    frames = b"".join(_pack(value, width) * channels for value in [*lead, *tone, *lead])
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return path
