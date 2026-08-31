"""Shared helpers for building throwaway media in tests."""

import math
import struct
import wave

from PIL import Image as PILImage


def make_image(path, size=(400, 300), colour=(200, 60, 60), mode="RGB", **save_kwargs):
    image = PILImage.new(mode, size, colour)
    image.save(path, **save_kwargs)
    return path


def make_wav(path, ms=250, rate=48_000, frequency=440.0):
    total = int(rate * ms / 1000)
    frames = b"".join(
        struct.pack("<h", int(12_000 * math.sin(2 * math.pi * frequency * n / rate)))
        for n in range(total)
    )
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return path
