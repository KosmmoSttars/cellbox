"""Where numba keeps compiled kernels: %LOCALAPPDATA%/KosmoStars/Cellbox/numba.

numba's own cache locators need the .py source on disk next to a stable path. A PyInstaller one-file
build has neither (sources are bytecode inside the exe, unpacked to a new temp folder every launch), so
without this locator the kernels would be recompiled on every start.

install() must run before numba is imported: numba reads the environment once, at import.
"""

import os
import sys
from pathlib import Path

from cellbox import __version__


def cache_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "KosmoStars" / "Cellbox" / "numba"


def cache_dir() -> Path:
    """This build's folder: running from source and the exe keep separate caches."""
    return cache_root() / ("exe" if getattr(sys, "frozen", False) else "source")


def install() -> None:
    os.environ["NUMBA_CACHE_LOCATOR_CLASSES"] = f"{__name__}.AppCacheLocator"


def _make_locator():
    from numba.core.caching import _CacheLocator

    class AppCacheLocator(_CacheLocator):
        """One stable cache folder per module, invalidated when the exe or the source changes."""

        def __init__(self, py_func, py_file: str):
            self._lineno = py_func.__code__.co_firstlineno
            self._path = str(cache_dir() / Path(py_file).stem)
            self._stamp_file = sys.executable if getattr(sys, "frozen", False) else py_file

        def get_cache_path(self) -> str:
            return self._path

        def get_source_stamp(self):
            try:
                st = os.stat(self._stamp_file)
            except OSError:
                return __version__
            return __version__, st.st_mtime, st.st_size

        def get_disambiguator(self) -> str:
            return str(self._lineno)

        @classmethod
        def from_function(cls, py_func, py_file):
            locator = cls(py_func, py_file)
            try:
                locator.ensure_cache_path()
            except OSError:
                return None   # read-only profile: compile every launch, still works
            return locator

    return AppCacheLocator


def __getattr__(name: str):
    # numba imports this class by name while it compiles; build it lazily so importing
    # this module (to call install()) does not import numba.
    if name == "AppCacheLocator":
        cls = _make_locator()
        globals()[name] = cls
        return cls
    raise AttributeError(name)
