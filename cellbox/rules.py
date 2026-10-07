"""Rule strings and presets.

Life-like rules use B/S notation: "B3/S23" means a dead cell is born with 3 live neighbors and a live
cell survives with 2 or 3. Generations rules add a state count: in "B2/S/C3" a live cell that does not
survive becomes "dying" and fades through C - 2 states before it is dead again.

Also accepted: the classic S/B form ("23/3") and the Generations S/B/C form ("345/2/4"),
lowercase letters, and no slashes ("b3s23").
"""

import re
from dataclasses import dataclass

MAX_STATES = 64   # the palette has room for this many states


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    birth: frozenset[int]
    survive: frozenset[int]
    states: int = 2              # 2 = Life-like, 3+ = Generations

    @property
    def is_generations(self) -> bool:
        return self.states > 2

    def __str__(self) -> str:
        text = f"B{_digits(self.birth)}/S{_digits(self.survive)}"
        return f"{text}/C{self.states}" if self.is_generations else text

    def describe(self) -> str:
        """Plain-English summary for the rules dialog."""
        born = ", ".join(map(str, sorted(self.birth))) or "never"
        stays = ", ".join(map(str, sorted(self.survive))) or "never"
        text = f"Born with {born} neighbors; survives with {stays}."
        if self.is_generations:
            text += f" Dying cells fade through {self.states - 2} more state{'s' if self.states > 3 else ''}."
        return text


def _digits(values: frozenset[int]) -> str:
    return "".join(str(v) for v in sorted(values))


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


def parse(text: str) -> Rule:
    """Parses a rule string or raises RuleError with a message fit for the user."""
    compact = re.sub(r"\s+", "", text).upper()
    if not compact:
        raise RuleError("Type a rule, for example B3/S23.")
    match = _BSC.match(compact) or _SBC.match(compact)
    if not match:
        raise RuleError("Use B/S notation like B3/S23, or B2/S/C3 for Generations.")
    birth = _neighbor_set(match["b"], text)
    survive = _neighbor_set(match["s"], text)
    states = _states(match["c"]) if match["c"] else 2
    return Rule(birth, survive, states)


@dataclass(frozen=True)
class Preset:
    name: str
    rule: Rule


def _preset(name: str, text: str) -> Preset:
    return Preset(name, parse(text))


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
}

PRESETS: tuple[Preset, ...] = tuple(p for group in PRESET_GROUPS.values() for p in group)
DEFAULT_RULE = PRESETS[0].rule


def preset_name(rule: Rule) -> str | None:
    return next((p.name for p in PRESETS if p.rule == rule), None)
