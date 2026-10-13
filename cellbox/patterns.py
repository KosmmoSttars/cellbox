"""Patterns: RLE files in and out, and the built-in library.

RLE is the format Golly and LifeWiki use:

    #N Glider
    #C The smallest spaceship.
    x = 3, y = 3, rule = B3/S23
    bob$2bo$3o!

Runs of cells are a count and a letter: b or . for empty, o for alive, A..X for states 1..24 and pA..yO
for states 25..255 (the multi-state letters Golly uses for Generations and Wireworld). $ ends a row and
! ends the pattern. Lenia patterns use the same letters for values 1..255 out of 255, as in Bert Chan's
Lenia catalogue.

The library lives in assets/patterns: one folder per rule family ("1 Life" sorts first and shows as
"Life"), RLE files inside named "NN Section - Name.rle", plus lenia.json with the Lenia creatures.
"""

import json
import re
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

import numpy as np

from cellbox.rules import AnyRule, LeniaRule, Rule, RuleError, parse

DEFAULT_RULE_TEXT = "B3/S23"   # RLE files without a rule are Conway's Life
LINE_WIDTH = 70


class PatternError(ValueError):
    pass


@dataclass(frozen=True)
class Pattern:
    name: str
    rule: AnyRule
    cells: np.ndarray = field(compare=False)   # uint8 states, or float32 values 0..1 for Lenia
    section: str = ""                          # library sub-heading
    comments: tuple[str, ...] = ()
    code: str | None = None                    # Lenia species code

    @property
    def width(self) -> int:
        return self.cells.shape[1]

    @property
    def height(self) -> int:
        return self.cells.shape[0]

    def rotated(self, quarter_turns: int = 1) -> "Pattern":
        """Turned clockwise by 90 degrees per quarter turn."""
        return replace(self, cells=np.ascontiguousarray(np.rot90(self.cells, -quarter_turns)))


# --- reading ------------------------------------------------------------------------------------

_HEADER = re.compile(r"^\s*x\s*=\s*(\d+)\s*,\s*y\s*=\s*(\d+)\s*(?:,\s*rule\s*=\s*(.*?))?\s*$", re.IGNORECASE)
_TOKEN = re.compile(r"(\d*)([b.o$!]|[p-y]?[A-X])")
_BODY = re.compile(r"(?:\d*(?:[b.o$]|[p-y]?[A-X]))*")


def _value(token: str) -> int:
    if token in "b.":
        return 0
    if token == "o":
        return 1
    if len(token) == 1:
        return ord(token) - ord("A") + 1
    return (ord(token[0]) - ord("p")) * 24 + ord(token[1]) - ord("A") + 25


def decode_cells(body: str, width: int = 0, height: int = 0) -> np.ndarray:
    """RLE body -> a 2D int array of states. Width and height come from the header when there is one."""
    rows: list[list[int]] = [[]]
    for count_text, token in _TOKEN.findall(re.sub(r"\s+", "", body)):
        count = int(count_text) if count_text else 1
        if token == "!":
            break
        if token == "$":
            rows.extend([] for _ in range(count))
        else:
            rows[-1].extend([_value(token)] * count)
    while rows and not rows[-1]:
        rows.pop()
    w = max(width, max((len(r) for r in rows), default=0))
    h = max(height, len(rows))
    out = np.zeros((h, w), dtype=np.int64)
    for y, row in enumerate(rows):
        out[y, :len(row)] = row
    return out


def _rule_from_header(text: str | None) -> AnyRule:
    text = (text or DEFAULT_RULE_TEXT).strip()
    if not text.upper().startswith("LENIA"):
        text = text.split(":", 1)[0]   # Golly's bounded-grid suffix, e.g. B3/S23:T100,100
    try:
        return parse(text)
    except RuleError as e:
        raise PatternError(f"Cellbox does not know the rule {text!r}.\n{e}")


def parse_rle(text: str, name: str = "Pattern") -> Pattern:
    comments: list[str] = []
    width = height = 0
    rule: AnyRule | None = None
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            kind, rest = stripped[1:2], stripped[2:].strip()
            if kind == "N" and rest:
                name = rest
            elif kind in "CcO" and rest:
                comments.append(rest)
            continue
        header = _HEADER.match(stripped) if rule is None and not body else None
        if header:
            width, height = int(header[1]), int(header[2])
            rule = _rule_from_header(header[3])
            continue
        body.append(stripped)
        if "!" in stripped:
            break
    if not body:
        raise PatternError("There is no pattern in this text: RLE needs a line like x = 3, y = 3 and cells.")
    if rule is None:
        rule = _rule_from_header(None)
    joined = re.sub(r"\s+", "", "".join(body)).split("!", 1)[0]
    if not _BODY.fullmatch(joined):
        raise PatternError("This does not look like an RLE pattern: cells are written with b, o, $ and !, "
                           "or with . and A to X for many-state rules.")
    states = decode_cells(joined, width, height)
    if isinstance(rule, LeniaRule):
        cells = (states.clip(0, 255) / 255).astype(np.float32)
    else:
        if states.max(initial=0) >= rule.states:
            raise PatternError(f"The pattern uses cell states the rule {rule} does not have.")
        cells = states.astype(np.uint8)
    if not cells.size or not cells.any():
        raise PatternError("The pattern is empty.")
    return Pattern(name, rule, cells, comments=tuple(comments))


def load_rle(path: Path) -> Pattern:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise PatternError(f"Could not read {path.name}.\n{e.strerror or e}")
    return parse_rle(text, name=path.stem)


# --- writing ------------------------------------------------------------------------------------

def _letter(value: int, two_state: bool) -> str:
    if two_state:
        return "o" if value else "b"
    if value == 0:
        return "."
    if value < 25:
        return chr(ord("A") + value - 1)
    return chr(ord("p") + (value - 25) // 24) + chr(ord("A") + (value - 25) % 24)


def encode_cells(states: np.ndarray, two_state: bool) -> str:
    """A 2D array of states -> an RLE body wrapped at LINE_WIDTH characters."""
    tokens: list[str] = []
    breaks = 0   # row ends not written yet: they merge into one "n$"
    for row in states.tolist():
        while row and row[-1] == 0:
            row.pop()
        if row and breaks:
            tokens.append(f"{breaks if breaks > 1 else ''}$")
            breaks = 0
        i = 0
        while i < len(row):
            j = i
            while j < len(row) and row[j] == row[i]:
                j += 1
            run = j - i
            tokens.append(f"{run if run > 1 else ''}{_letter(row[i], two_state)}")
            i = j
        breaks += 1
    tokens.append("!")
    lines, line = [], ""
    for token in tokens:
        if len(line) + len(token) > LINE_WIDTH:
            lines.append(line)
            line = ""
        line += token
    lines.append(line)
    return "\n".join(lines)


def to_rle(pattern: Pattern) -> str:
    rule = pattern.rule
    if isinstance(rule, LeniaRule):
        states = np.rint(pattern.cells * 255).astype(np.int64)
    else:
        states = pattern.cells.astype(np.int64)
    two_state = isinstance(rule, Rule) and not rule.is_generations
    head = [f"#N {pattern.name}"] + [f"#C {c}" for c in pattern.comments]
    head.append(f"x = {pattern.width}, y = {pattern.height}, rule = {rule.rle_text()}")
    return "\n".join(head) + "\n" + encode_cells(states, two_state) + "\n"


# --- the library ----------------------------------------------------------------------------------

def patterns_dir() -> Path:
    from cellbox.sound import assets_dir
    return assets_dir() / "patterns"


_FILE_NAME = re.compile(r"^\d+\s+(?P<section>.+?)\s+-\s+(?P<name>.+)$")


@cache
def library() -> dict[str, tuple[Pattern, ...]]:
    """Menu group -> patterns, in menu order."""
    groups: dict[str, tuple[Pattern, ...]] = {}
    root = patterns_dir()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        title = re.sub(r"^\d+\s+", "", folder.name)
        items = []
        for path in sorted(folder.glob("*.rle")):
            match = _FILE_NAME.match(path.stem)
            section = match["section"] if match else ""
            pattern = load_rle(path)
            items.append(replace(pattern, section=section))
        groups[title] = tuple(items)
    lenia = root / "lenia.json"
    if lenia.exists():
        data = json.loads(lenia.read_text(encoding="utf-8"))
        species = []
        for s in data["species"]:
            rule = parse(s["rule"])
            cells = (decode_cells(s["cells"]).clip(0, 255) / 255).astype(np.float32)
            species.append(Pattern(s["name"], rule, cells, section=s["section"],
                                   comments=(s["latin"], data["credit"]), code=s["code"]))
        groups["Lenia"] = tuple(species)
    return groups


def species(code: str) -> Pattern | None:
    return next((p for p in library().get("Lenia", ()) if p.code == code), None)
