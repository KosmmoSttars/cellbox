"""Cellbox entry point.

    python main.py               open the window
    python main.py --self-check  write cellbox_check.txt next to the app and exit (used by tools/build.py)
"""

import sys
import time
import traceback
from pathlib import Path

from cellbox import jitcache

jitcache.install()   # before anything imports numba


def self_check() -> int:
    base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    lines = []
    ok = True
    try:
        from cellbox.splash import close_unpacking_splash
        close_unpacking_splash()
        t = time.perf_counter()
        from cellbox.engine import Field
        from cellbox.rules import parse
        lines.append(f"engine     loaded in {time.perf_counter() - t:.2f} s")
        field = Field(16, parse("B3/S23"))
        for y, x in ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2)):
            field.state[y, x] = 1
        start = field.state.copy()
        field.step(64)
        glider_ok = (field.state == start).all() and field.population == 5
        lines.append(f"glider     {'back home after 64 steps' if glider_ok else 'WRONG'}")
        big = Field(1024)
        big.seed(0.3, spot=False, seed=1)
        t = time.perf_counter()
        big.step(20)
        lines.append(f"speed      {20 / (time.perf_counter() - t):.0f} steps/s at 1024 x 1024")
        cache = list(jitcache.cache_dir().rglob("*.nbi"))
        lines.append(f"jit cache  {len(cache)} index file(s) in {jitcache.cache_dir()}")
        from cellbox.sound import SOUND_FILES, assets_dir
        missing = [f for f in SOUND_FILES.values() if not (assets_dir() / "sounds" / f).exists()]
        lines.append(f"sounds     {'all present' if not missing else 'missing ' + ', '.join(missing)}")
        ok = bool(glider_ok) and bool(cache) and not missing
    except Exception as e:  # report anything; the build must see it
        ok = False
        lines.append(f"error      {e!r}")
    lines.insert(0, f"self-check {'passed' if ok else 'FAILED'}")
    (base / "cellbox_check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()

    from PyQt6.QtWidgets import QApplication

    from cellbox.dialogs import ErrorDialog
    from cellbox.icon import app_icon
    from cellbox.splash import Splash
    from cellbox.win95 import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Cellbox")
    app.setWindowIcon(app_icon())
    apply_theme(app)

    splash = Splash()
    windows = []

    def open_main() -> None:
        from cellbox.settings import Settings
        from cellbox.ui import MainWindow

        window = MainWindow(Settings())
        windows.append(window)
        window.show()
        splash.close()

    def fail(message: str) -> None:
        splash.close()
        ErrorDialog("Cellbox", f"The cell engine could not start.\n\n{message}").exec()
        app.quit()

    def excepthook(kind, value, tb) -> None:
        # PyQt aborts the app on an exception in a slot; show it and keep running instead.
        traceback.print_exception(kind, value, tb)
        ErrorDialog("Cellbox", f"Something went wrong.\n\n{kind.__name__}: {value}",
                    windows[0] if windows else None).exec()

    sys.excepthook = excepthook
    splash.finished.connect(open_main)
    splash.failed.connect(fail)
    splash.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
