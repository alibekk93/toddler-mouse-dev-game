"""QSoundEffect pool with a master volume cap.

Three traps this exists to avoid (ARCHITECTURE §4.2):

- a `QSoundEffect` that gets garbage collected mid-playback fails **silently**, so every
  effect is kept alive in a dict for the life of the player;
- WAVs must be pre-loaded, so the caller warms up the next round's audio during the
  current round's celebration;
- repeats must never stack, so voice playback is a single channel and a response can be
  queued behind whatever is still talking (UX §3: never cut audio off).

She sits 40cm from the speakers, so everything passes through a cap she cannot change.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

VOLUME_CEILING = 0.85  # the master_volume setting is a fraction of this, never above it
_POLL_MS = 40

try:  # QtMultimedia needs a working audio backend; a machine without one still plays
    from PySide6.QtMultimedia import QSoundEffect

    AVAILABLE = True
    UNAVAILABLE_REASON = ""
except Exception as exc:  # noqa: BLE001
    QSoundEffect = None  # type: ignore[assignment]
    AVAILABLE = False
    UNAVAILABLE_REASON = str(exc)


class Player(QObject):
    """Owns every loaded sound. One voice channel, many simultaneous effects."""

    voice_finished = Signal()

    def __init__(self, master_volume: float = 0.8, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._volume = max(0.0, min(1.0, master_volume)) * VOLUME_CEILING
        self._effects: dict[str, object] = {}
        self._voice_key: str | None = None
        self._queued = None

        self._poll = QTimer(self)
        self._poll.setInterval(_POLL_MS)
        self._poll.timeout.connect(self._check_voice)

    # -- loading -----------------------------------------------------------

    def preload(self, path: Path | str) -> str | None:
        """Load a WAV and keep it alive. Returns the key to play it by."""
        key = str(path)
        if key in self._effects:
            return key
        if not AVAILABLE or not Path(key).is_file():
            return None
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(Path(key).resolve())))
        effect.setVolume(self._volume)
        self._effects[key] = effect
        return key

    def preload_all(self, paths) -> None:
        for path in paths:
            self.preload(path)

    # -- playing -----------------------------------------------------------

    def play(self, path: Path | str | None, volume_scale: float = 1.0) -> None:
        """Fire and forget. Several of these can overlap."""
        if path is None:
            return
        key = self.preload(path)
        if key is None:
            return
        effect = self._effects[key]
        effect.setVolume(max(0.0, min(1.0, self._volume * volume_scale)))
        effect.play()

    def play_voice(self, path: Path | str | None) -> None:
        """Play a recording on the single voice channel, replacing whatever was there.

        Only one voice at a time, ever: two overlapping questions are confusing.
        """
        self.stop_voice()
        if path is None:
            return
        key = self.preload(path)
        if key is None:
            self.voice_finished.emit()
            return
        self._voice_key = key
        self._effects[key].play()
        self._poll.start()

    def stop_voice(self) -> None:
        """Cut the voice channel, dropping anything queued behind it.

        A callback queued by `after_voice` is waiting for *this* recording to finish. If
        the recording is cut deliberately — she clicked, so the question has done its job
        — then what was waiting on it is stale, and leaving it set would fire it against
        whatever plays next.
        """
        if self._voice_key and self._voice_key in self._effects:
            self._effects[self._voice_key].stop()
        self._voice_key = None
        self._queued = None
        self._poll.stop()

    def is_voice_playing(self) -> bool:
        if not self._voice_key:
            return False
        effect = self._effects.get(self._voice_key)
        return bool(effect and effect.isPlaying())

    def after_voice(self, callback) -> None:
        """Run `callback` once the voice channel is free.

        UX §3: if the question is still playing when she clicks, let the click resolve
        but let the audio finish, then play the response. Never cut a voice off.
        """
        if not self.is_voice_playing():
            callback()
            return
        self._queued = callback
        self._poll.start()

    def _check_voice(self) -> None:
        if self.is_voice_playing():
            return
        self._voice_key = None
        self._poll.stop()
        queued, self._queued = self._queued, None
        self.voice_finished.emit()
        if queued is not None:
            queued()

    # -- lifecycle ---------------------------------------------------------

    def set_master_volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value)) * VOLUME_CEILING
        for effect in self._effects.values():
            effect.setVolume(self._volume)

    def stop_all(self) -> None:
        self.stop_voice()
        self._queued = None
        for effect in self._effects.values():
            effect.stop()


class Sfx:
    """The app's own sound effects, by name, resolved once (UX §4)."""

    def __init__(self, player: Player) -> None:
        self._player = player
        folder = Path(__file__).resolve().parent.parent / "assets" / "sfx"
        self.paths = {p.stem: p for p in folder.glob("*.wav")}
        player.preload_all(self.paths.values())

    def play(self, name: str, volume_scale: float = 1.0) -> None:
        self._player.play(self.paths.get(name), volume_scale)
