"""Microphone capture for the record dialog (SPEC §4.3).

Built on QtMultimedia's `QAudioSource` in pull mode. ARCHITECTURE §1 originally named
`sounddevice`+`soundfile`+`numpy`, and its objection was to *QMediaRecorder* — the
high-level encoder. `QAudioSource` is the low-level half: it hands over raw PCM frames,
which is all the level meter and the silence trimmer ever needed, and QtMultimedia is
already a dependency (`audio/player.py`).

Two things this module must get right, both from ARCHITECTURE §4.6:

- Windows 11 asks for microphone consent, and a refused app records silence. An empty or
  silent buffer is reported as a failure, **never** saved as a 0-byte WAV.
- A machine with no microphone at all disables the record button with a plain sentence;
  importing a file still works.
"""

import shutil
import tempfile
import wave
from array import array
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ..core.importer import FULL_SCALE, MAX_AUDIO_MS, ImportRejected, normalise_audio, to_int16

try:  # the same guard player.py uses: a machine without an audio backend still runs
    from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

    IMPORT_ERROR = ""
except Exception as exc:  # noqa: BLE001
    QAudioFormat = QAudioSource = QMediaDevices = None  # type: ignore[assignment]
    IMPORT_ERROR = str(exc)

RATE = 48_000


def unavailable_reason() -> str:
    """Empty when recording is possible, otherwise a sentence fit to show a parent.

    Checked on demand rather than at import: a USB microphone plugged in after the app
    started should work without a restart.
    """
    if IMPORT_ERROR:
        return f"Audio is unavailable on this machine, so recording is off ({IMPORT_ERROR})."
    if QMediaDevices.defaultAudioInput().isNull():
        return "No microphone found. Plug one in, or import a sound file instead."
    return ""


def _sample_width(fmt) -> int:
    """Bytes per sample for a QAudioFormat, or 0 for a format we cannot record."""
    formats = QAudioFormat.SampleFormat
    widths = {formats.UInt8: 1, formats.Int16: 2, formats.Int32: 4, formats.Float: 4}
    return widths.get(fmt.sampleFormat(), 0)


def _float_to_int16(raw: bytes) -> array:
    """Float32 frames, the one input format `wave` cannot store, folded to int16."""
    floats = array("f")
    floats.frombytes(raw[: len(raw) - len(raw) % 4])
    return array("h", (int(max(-1.0, min(1.0, value)) * (FULL_SCALE - 1)) for value in floats))


class Recorder(QObject):
    """One take. `start()`, watch `level`, `stop()`, then `finished` or `failed`."""

    level = Signal(float)  # 0..1 peak of the last chunk, for the meter
    finished = Signal(object)  # Path to a normalised WAV, ready to preview
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source = None
        self._io = None
        self._format = None
        self._buffer = bytearray()  # int16, interleaved at `self._channels`
        self._carry = b""  # a partial frame split across two reads
        self._channels = 1
        self._rate = RATE
        self._scratch = Path(tempfile.mkdtemp(prefix="buska-rec-"))
        self._takes = 0
        self._closing = False

        # The 10s cap lives here so `normalise_audio`'s limit can never fire on a
        # recording: it stops the take rather than rejecting it after the fact.
        self._cap = QTimer(self)
        self._cap.setSingleShot(True)
        self._cap.setInterval(MAX_AUDIO_MS)
        self._cap.timeout.connect(self.stop)

    # -- capture -----------------------------------------------------------

    def is_recording(self) -> bool:
        return self._source is not None

    def start(self) -> bool:
        """Open the input stream. Returns False (with `failed`) if it cannot be opened."""
        reason = unavailable_reason()
        if reason:
            self.failed.emit(reason)
            return False
        if self.is_recording():
            return True

        device = QMediaDevices.defaultAudioInput()
        fmt = QAudioFormat()
        fmt.setSampleRate(RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            # Whatever the device does offer is fine: normalise_audio folds any channel
            # count to mono, and the source rate is kept rather than resampled.
            fmt = device.preferredFormat()
        if not _sample_width(fmt):
            self.failed.emit("The microphone offers no sample format this app can record.")
            return False

        self._format = fmt
        self._channels = max(1, fmt.channelCount())
        self._rate = fmt.sampleRate() or RATE
        self._buffer.clear()
        self._carry = b""

        self._source = QAudioSource(device, fmt, self)
        self._io = self._source.start()
        if self._io is None:
            self._source = None
            self.failed.emit("The microphone could not be opened. Another app may be using it.")
            return False
        self._io.readyRead.connect(self._drain)
        self._cap.start()
        return True

    def _drain(self) -> None:
        raw = self._carry + bytes(self._io.readAll().data())
        width = _sample_width(self._format)
        usable = len(raw) - len(raw) % width
        self._carry, raw = raw[usable:], raw[:usable]
        if not raw:
            return

        if self._format.sampleFormat() == QAudioFormat.SampleFormat.Float:
            samples = _float_to_int16(raw)
        else:
            samples = to_int16(raw, width)
        self._buffer += samples.tobytes()
        self.level.emit(max((abs(v) for v in samples), default=0) / FULL_SCALE)

    def stop(self) -> None:
        """End the take and hand the normalised clip to `finished`."""
        if not self.is_recording():
            return
        self._cap.stop()
        self._source.stop()
        self._source = None
        self._io = None
        self.level.emit(0.0)

        raw, self._buffer = bytes(self._buffer), bytearray()
        if not raw:
            # ARCHITECTURE §4.6: a refused microphone permission looks exactly like this.
            self.failed.emit(
                "No audio was captured. Check the microphone is plugged in, and that "
                "Windows lets this app use it (Settings > Privacy > Microphone)."
            )
            return

        self._takes += 1
        destination = self._scratch / f"take-{self._takes}.wav"
        # ~0.2s of pure-Python passes over a 10s clip: off the UI thread it goes.
        QThreadPool.globalInstance().start(
            lambda: self._normalise(raw, self._rate, self._channels, destination)
        )

    def _normalise(self, raw: bytes, rate: int, channels: int, destination: Path) -> None:
        """Worker thread. Signals cross back to the UI thread as queued connections."""
        if self._closing:
            return  # the dialog went away mid-trim; there is nobody to hand it to
        source = destination.with_suffix(".raw.wav")
        try:
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(channels)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes(raw)
            data, _duration_ms = normalise_audio(source)
        except (OSError, wave.Error, ImportRejected) as exc:
            self.failed.emit(str(exc))
            return
        finally:
            source.unlink(missing_ok=True)

        destination.write_bytes(data)
        self.finished.emit(destination)

    # -- lifecycle ---------------------------------------------------------

    def cleanup(self) -> None:
        """Abort whatever is in flight and drop the scratch takes.

        Deliberately *not* `stop()`: a take still running when the dialog closes is
        discarded, not normalised and handed to a dialog that no longer exists.
        """
        self._closing = True
        self._cap.stop()
        if self._source is not None:
            self._source.stop()
            self._source = None
            self._io = None
        self._buffer = bytearray()
        shutil.rmtree(self._scratch, ignore_errors=True)
