"""Win95-style sound effects from WAV files in assets/sounds/ (made by tools/make_sounds.py).

Any file can be replaced with your own 16-bit PCM WAV without touching the code.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl
from PyQt6.QtMultimedia import QSoundEffect

SOUND_FILES = {
    "click": "click.wav",          # toolbar buttons
    "error": "error.wav",          # a rule that does not parse
}
POOL_SIZE = 3                      # overlapping copies per sound (rapid clicks)
VOLUME = 0.6


def assets_dir() -> Path:
    """Bundled inside the one-file exe, else in the project."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


class SoundBank(QObject):
    def __init__(self, enabled: bool, parent: QObject | None = None):
        super().__init__(parent)
        self.enabled = enabled
        self._pools: dict[str, list[QSoundEffect]] = {}
        self._next: dict[str, int] = {}
        folder = assets_dir() / "sounds"
        for name, filename in SOUND_FILES.items():
            path = folder / filename
            if not path.exists():
                continue
            pool = []
            for _ in range(POOL_SIZE):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))   # preload: the first play is instant
                effect.setVolume(VOLUME)
                pool.append(effect)
            self._pools[name] = pool
            self._next[name] = 0

    def play(self, name: str) -> None:
        pool = self._pools.get(name)
        if not self.enabled or not pool:
            return
        i = self._next[name]
        self._next[name] = (i + 1) % len(pool)
        pool[i].play()
