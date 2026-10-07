"""Startup window: loads numba and the cell engine in the background behind a Win95 progress bar.

The first launch compiles the engine (a few seconds); later launches load it from the cache.
"""

import threading
import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout

from cellbox import jitcache
from cellbox.icon import icon_pixmap
from cellbox.win95 import ProgressBar, Win95Frame, ui_font

# (message, share of the bar the stage fills, expected seconds for a cold start)
STAGES = (
    ("Loading numba...", 35, 1.5),
    ("Compiling the cell engine...", 60, 3.0),
    ("Starting up...", 5, 0.2),
)
CACHED_MESSAGE = "Loading the cell engine..."


def close_unpacking_splash() -> None:
    try:
        import pyi_splash   # only exists inside the one-file exe
    except ImportError:
        return
    pyi_splash.close()


def _engine_cached() -> bool:
    return any(jitcache.cache_dir().rglob("*.nbi"))


class Splash(Win95Frame):
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__("Cellbox", closable=False)
        self.always_active = True
        self.setWindowTitle("Cellbox")
        art = QLabel()
        art.setPixmap(icon_pixmap(48))
        name = QLabel("Cellbox")
        name.setFont(ui_font(bold=True, size=16))
        tagline = QLabel("Cellular automata in a Windows 95 box")
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(art)
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(name)
        words.addWidget(tagline)
        head.addLayout(words, 1)

        self._message = QLabel(STAGES[0][0])
        self._bar = ProgressBar()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        lay.addLayout(head)
        lay.addWidget(self._message)
        lay.addWidget(self._bar)
        self.setFixedWidth(340)
        self.adjustSize()
        # Centered on the whole screen, exactly where the exe's unpacking splash image was.
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)

        self._cached = _engine_cached()
        self._stage = 0
        self._stage_started = time.monotonic()
        self._done_stages = 0          # written by the loader thread
        self._error: str | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def still_image(self, message: str) -> QImage:
        """The splash as a 1x picture: the one-file exe shows it while it unpacks (see tools/build.py)."""
        self._message.setText(message)
        image = QImage(self.size(), QImage.Format.Format_RGB32)
        self.render(image)
        self._message.setText(STAGES[0][0])
        return image

    def start(self) -> None:
        self.show()
        close_unpacking_splash()
        threading.Thread(target=self._load, daemon=True).start()
        self._timer.start(30)

    def _load(self) -> None:
        try:
            import numba  # noqa: F401
            self._done_stages = 1
            from cellbox import engine
            engine.warm_up()
            self._done_stages = 2
        except Exception as e:  # shown to the user; the app cannot run without the engine
            self._error = f"{type(e).__name__}: {e}"

    def _tick(self) -> None:
        if self._error is not None:
            self._timer.stop()
            self.failed.emit(self._error)
            return
        while self._stage < self._done_stages:
            self._stage += 1
            self._stage_started = time.monotonic()
        base = sum(share for _, share, _ in STAGES[:self._stage])
        if self._stage >= len(STAGES) - 1:
            self._bar.set_value(100)
            self._message.setText(STAGES[-1][0])
            self._timer.stop()
            QTimer.singleShot(150, self.finished.emit)
            return
        message, share, seconds = STAGES[self._stage]
        if self._stage == 1 and self._cached:
            message, seconds = CACHED_MESSAGE, 0.5
        # Ease toward the end of the stage without ever reaching it: the thread says when it is done.
        t = (time.monotonic() - self._stage_started) / seconds
        self._bar.set_value(base + share * (1 - 1 / (1 + 1.6 * t)))
        self._message.setText(message)
