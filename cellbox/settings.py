"""Settings kept between launches in %APPDATA%/KosmoStars/Cellbox.ini. The cells themselves are not saved."""

import random
from dataclasses import dataclass

from PyQt6.QtCore import QByteArray, QSettings

from cellbox.engine import DEFAULT_SIZE, SIZES
from cellbox.rules import DEFAULT_RULE, Rule, RuleError, parse

SPEED_MAX = 61           # the slider's last notch: as fast as the machine allows
DEFAULT_SPEED = 30       # steps per second


def open_settings() -> QSettings:
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "KosmoStars", "Cellbox")


def new_seed() -> int:
    return random.randrange(1, 1_000_000)


@dataclass
class SeedOptions:
    density: int = 30          # percent of live cells in the seeded zone
    spot: bool = False         # only a disc in the center instead of the whole field
    seed: int = 1
    fixed: bool = False        # reuse the same seed on every reseed instead of a new one


class Settings:
    def __init__(self):
        self.store = open_settings()

    def _int(self, key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(self.store.value(key, default))))
        except (TypeError, ValueError):
            return default

    def _bool(self, key: str, default: bool) -> bool:
        return str(self.store.value(key, default)).lower() == "true"

    # --- rule, field size, speed ----------------------------------------------------------

    @property
    def rule(self) -> Rule:
        try:
            return parse(str(self.store.value("rule", str(DEFAULT_RULE))))
        except RuleError:
            return DEFAULT_RULE

    @rule.setter
    def rule(self, rule: Rule) -> None:
        self.store.setValue("rule", str(rule))

    @property
    def size(self) -> int:
        size = self._int("size", DEFAULT_SIZE, 0, 1 << 20)
        return size if size in SIZES else DEFAULT_SIZE

    @size.setter
    def size(self, size: int) -> None:
        self.store.setValue("size", size)

    @property
    def speed(self) -> int:
        return self._int("speed", DEFAULT_SPEED, 1, SPEED_MAX)

    @speed.setter
    def speed(self, speed: int) -> None:
        self.store.setValue("speed", speed)

    # --- seeding ---------------------------------------------------------------------------

    @property
    def seeding(self) -> SeedOptions:
        return SeedOptions(
            density=self._int("seed/density", 30, 1, 100),
            spot=self._bool("seed/spot", False),
            seed=self._int("seed/seed", 1, 0, 2**31 - 1),
            fixed=self._bool("seed/fixed", False),
        )

    @seeding.setter
    def seeding(self, options: SeedOptions) -> None:
        self.store.setValue("seed/density", options.density)
        self.store.setValue("seed/spot", options.spot)
        self.store.setValue("seed/seed", options.seed)
        self.store.setValue("seed/fixed", options.fixed)

    # --- window and sound ------------------------------------------------------------------

    @property
    def geometry(self) -> QByteArray | None:
        value = self.store.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    @geometry.setter
    def geometry(self, value: QByteArray) -> None:
        self.store.setValue("window/geometry", value)

    @property
    def maximized(self) -> bool:
        return self._bool("window/maximized", False)

    @maximized.setter
    def maximized(self, on: bool) -> None:
        self.store.setValue("window/maximized", on)

    @property
    def sound(self) -> bool:
        return self._bool("sound/enabled", True)

    @sound.setter
    def sound(self, on: bool) -> None:
        self.store.setValue("sound/enabled", on)
