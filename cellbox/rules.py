"""Rule strings and presets.

Three families of rules:

- Life-like rules use B/S notation: "B3/S23" means a dead cell is born with 3 live neighbors and a live
  cell survives with 2 or 3. Generations rules add a state count: in "B2/S/C3" a live cell that does not
  survive becomes "dying" and fades through C - 2 states before it is dead again.
  Also accepted: the classic S/B form ("23/3") and the Generations S/B/C form ("345/2/4"),
  lowercase letters, and no slashes ("b3s23").
- Wireworld ("WireWorld"): electrons running along wires, the classic four-state computer automaton.
- Lenia ("Lenia R=13 T=10 m=0.15 s=0.015 b=1"): a continuous automaton. Cells hold a value from 0 to 1,
  each step every cell looks at a smooth ring of neighbors R cells across and grows or shrinks by 1/T of
  a bell curve centered on m with width s. b lists the peak heights of the kernel's rings, outer last
  ("b=1/2;1" is two rings). Kernel and growth are Bert Chan's polynomial (quad4) shapes.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar, Union

MAX_STATES = 64   # the palette has room for this many states
LENIA_SHADES = 256   # Lenia values are drawn in this many shades
MAX_RADIUS = 64
MAX_RINGS = 4


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    """A Life-like (2 states) or Generations (3+ states) rule."""
    birth: frozenset[int]
    survive: frozenset[int]
    states: int = 2              # 2 = Life-like, 3+ = Generations

    family: ClassVar[str] = "life"

    @property
    def is_generations(self) -> bool:
        return self.states > 2

    def __str__(self) -> str:
        text = f"B{_digits(self.birth)}/S{_digits(self.survive)}"
        return f"{text}/C{self.states}" if self.is_generations else text

    def rle_text(self) -> str:
        """The spelling for an RLE header: Golly reads Generations rules in the S/B/C form."""
        if self.is_generations:
            return f"{_digits(self.survive)}/{_digits(self.birth)}/{self.states}"
        return str(self)

    def describe(self) -> str:
        """Plain-English summary for the rules dialog."""
        born = ", ".join(map(str, sorted(self.birth))) or "never"
        stays = ", ".join(map(str, sorted(self.survive))) or "never"
        text = f"Born with {born} neighbors; survives with {stays}."
        if self.is_generations:
            text += f" Dying cells fade through {self.states - 2} more state{'s' if self.states > 3 else ''}."
        return text


@dataclass(frozen=True)
class Wireworld:
    """Cell states: 0 empty, 1 electron head, 2 electron tail, 3 wire."""
    family: ClassVar[str] = "wireworld"
    states: ClassVar[int] = 4
    is_generations: ClassVar[bool] = False

    EMPTY: ClassVar[int] = 0
    HEAD: ClassVar[int] = 1
    TAIL: ClassVar[int] = 2
    WIRE: ClassVar[int] = 3

    def __str__(self) -> str:
        return "WireWorld"

    def rle_text(self) -> str:
        return str(self)

    def describe(self) -> str:
        return ("Electrons run along wires: a head becomes a tail, a tail becomes wire again, and wire "
                "lights up when one or two heads touch it.")


@dataclass(frozen=True)
class LeniaRule:
    radius: int = 13             # R: kernel radius in cells
    period: int = 10             # T: steps per unit of time; each step adds 1/T of the growth
    mu: float = 0.15             # m: the neighborhood sum that grows fastest
    sigma: float = 0.015         # s: how far from m a cell still grows
    peaks: tuple[Fraction, ...] = (Fraction(1),)   # b: ring heights, inner ring first

    family: ClassVar[str] = "lenia"
    states: ClassVar[int] = LENIA_SHADES
    is_generations: ClassVar[bool] = False

    def __str__(self) -> str:
        peaks = ";".join(str(p) for p in self.peaks)
        return f"Lenia R={self.radius} T={self.period} m={_num(self.mu)} s={_num(self.sigma)} b={peaks}"

    def rle_text(self) -> str:
        return str(self)

    def describe(self) -> str:
        rings = len(self.peaks)
        return (f"Continuous cells. Each one weighs a ring{'s' if rings > 1 else ''} of neighbors "
                f"{self.radius} cells out and grows fastest when that sum is near {_num(self.mu)} "
                f"(width {_num(self.sigma)}), {self.period} steps per unit of time.")


AnyRule = Union[Rule, Wireworld, LeniaRule]


def _digits(values: frozenset[int]) -> str:
    return "".join(str(v) for v in sorted(values))


def _num(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _neighbor_set(text: str, rule: str) -> frozenset[int]:
    if any(ch not in "012345678" for ch in text):
        raise RuleError(f"Neighbor counts in {rule!r} must be digits 0 to 8.")
    return frozenset(int(ch) for ch in text)


def _states(text: str) -> int:
    count = int(text)
    if count < 2 or count > MAX_STATES:
        raise RuleError(f"The state count must be between 2 and {MAX_STATES}.")
    return count


_BSC = re.compile(r"^B(?P<b>\d*)/?S(?P<s>\d*)(?:/?[CG](?P<c>\d+))?$")
_SBC = re.compile(r"^(?P<s>\d*)/(?P<b>\d*)(?:/(?P<c>\d+))?$")
_LENIA_PARAM = re.compile(r"([RTMSB])\s*=?\s*([0-9.,;/]+)", re.IGNORECASE)


def _parse_lenia(text: str) -> LeniaRule:
    params: dict[str, str] = {}
    for key, value in _LENIA_PARAM.findall(text):
        params[key.upper()] = value.strip(",;")
    missing = [k for k in "RTMS" if k not in params]
    if missing:
        raise RuleError("A Lenia rule needs R, T, m and s, for example Lenia R=13 T=10 m=0.15 s=0.015 b=1.")
    try:
        radius, period = int(params["R"]), int(params["T"])
        mu, sigma = float(params["M"]), float(params["S"])
        peaks = tuple(Fraction(p) for p in re.split(r"[,;]", params.get("B", "1")) if p)
    except (ValueError, ZeroDivisionError):
        raise RuleError("Lenia numbers: R and T whole numbers, m and s decimals, b fractions like 1/2;1.")
    if not 2 <= radius <= MAX_RADIUS:
        raise RuleError(f"Lenia's R must be between 2 and {MAX_RADIUS}.")
    if not 1 <= period <= 1000:
        raise RuleError("Lenia's T must be between 1 and 1000.")
    if not 0 < mu < 1 or not 0 < sigma < 1:
        raise RuleError("Lenia's m and s must be between 0 and 1.")
    if not 1 <= len(peaks) <= MAX_RINGS or any(p < 0 or p > 1 for p in peaks) or not any(peaks):
        raise RuleError(f"Lenia's b lists 1 to {MAX_RINGS} ring heights from 0 to 1.")
    return LeniaRule(radius, period, mu, sigma, peaks)


def parse(text: str) -> AnyRule:
    """Parses a rule string or raises RuleError with a message fit for the user."""
    stripped = text.strip()
    word = stripped.split(None, 1)[0].upper() if stripped else ""
    if word.replace("-", "") == "WIREWORLD":
        return Wireworld()
    if word.startswith("LENIA"):
        return _parse_lenia(stripped[5:])
    compact = re.sub(r"\s+", "", text).upper()
    if not compact:
        raise RuleError("Type a rule, for example B3/S23.")
    match = _BSC.match(compact) or _SBC.match(compact)
    if not match:
        raise RuleError("Use B/S notation like B3/S23, B2/S/C3 for Generations, WireWorld, or a Lenia rule.")
    birth = _neighbor_set(match["b"], text)
    survive = _neighbor_set(match["s"], text)
    states = _states(match["c"]) if match["c"] else 2
    return Rule(birth, survive, states)


@dataclass(frozen=True)
class Preset:
    name: str
    rule: AnyRule
    species: str | None = None   # Lenia: the creature (by its code in the pattern library) a reseed scatters


def _preset(name: str, text: str, species: str | None = None) -> Preset:
    return Preset(name, parse(text), species)


PRESET_GROUPS: dict[str, tuple[Preset, ...]] = {
    "Classic": (
        _preset("Conway's Life", "B3/S23"),
        _preset("HighLife", "B36/S23"),
        _preset("Day & Night", "B3678/S34678"),
        _preset("Seeds", "B2/S"),
    ),
    "Growth and mazes": (
        _preset("Maze", "B3/S12345"),
        _preset("Coral", "B3/S45678"),
        _preset("Diamoeba", "B35678/S5678"),
        _preset("Anneal", "B4678/S35678"),
    ),
    "Generations": (
        _preset("Brian's Brain", "B2/S/C3"),
        _preset("Star Wars", "B2/S345/C4"),
        _preset("Fireworks", "B13/S2/C21"),
        _preset("Bloomerang", "B34678/S234/C24"),
    ),
    "Wireworld": (
        _preset("Wireworld", "WireWorld"),
    ),
    "Lenia": (
        _preset("Orbium", "Lenia R=13 T=10 m=0.15 s=0.015 b=1", "O2u"),
        _preset("Scutium", "Lenia R=13 T=10 m=0.29 s=0.045 b=1", "S1s"),
        _preset("Gyropteron", "Lenia R=13 T=10 m=0.283 s=0.0481 b=1", "PG1a"),
        _preset("Helicium", "Lenia R=13 T=10 m=0.35 s=0.06 b=1", "H3s"),
        _preset("Kronium", "Lenia R=18 T=10 m=0.24 s=0.029 b=1;1/3", "K4s"),
        _preset("Hydrogeminium", "Lenia R=27 T=10 m=0.28 s=0.042 b=11/12;11/12;1", "3GH2s"),
    ),
}

PRESETS: tuple[Preset, ...] = tuple(p for group in PRESET_GROUPS.values() for p in group)
DEFAULT_RULE = PRESETS[0].rule


def preset_for(rule: AnyRule) -> Preset | None:
    return next((p for p in PRESETS if p.rule == rule), None)


def preset_name(rule: AnyRule) -> str | None:
    preset = preset_for(rule)
    return preset.name if preset else None
