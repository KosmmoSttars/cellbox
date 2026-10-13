"""Builds the Wireworld circuits of the pattern library and checks that they work.

    python tools/make_circuits.py

Writes RLE files into assets/patterns/3 Wireworld. Every circuit is run before it is written: the clocks
must tick at their period, a diode must pass one way and block the other, the gates must give exactly the
outputs of an ideal gate. The diode and gate shapes were found by brute-force search over small shapes,
keeping only those that never multiply, reflect or leak electrons back into an input.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cellbox import jitcache  # noqa: E402

jitcache.install()

from cellbox.engine import _wire_step  # noqa: E402
from cellbox.patterns import Pattern, to_rle  # noqa: E402
from cellbox.rules import Wireworld  # noqa: E402

OUT = ROOT / "assets" / "patterns" / "3 Wireworld"
EMPTY, HEAD, TAIL, WIRE = 0, 1, 2, 3

# Shapes as rows relative to an anchor row, columns from the anchor column; '#' is wire.
DIODE = {-1: ".###", 0: "##", 1: ".###"}          # wire in from the left up to the anchor, out from +4
OR_GATE = {-2: "#", -1: ".#.##", 0: "###", 1: ".#.##", 2: "#"}               # inputs end one left of
XOR_GATE = {-3: "##", -2: "..#", -1: ".####", 0: ".#..#", 1: ".####", 2: "..#", 3: "##"}   # the anchor


class Board:
    def __init__(self, h: int, w: int):
        self.g = np.zeros((h, w), dtype=np.uint8)

    def path(self, *points: tuple[int, int]) -> None:
        """An orthogonal wire through the points."""
        for (y0, x0), (y1, x1) in zip(points, points[1:]):
            assert y0 == y1 or x0 == x1, "wires run straight"
            self.g[min(y0, y1):max(y0, y1) + 1, min(x0, x1):max(x0, x1) + 1] = WIRE

    def shape(self, rows: dict[int, str], y: int, x: int, mirrored: bool = False) -> None:
        for dy, row in rows.items():
            for dx, ch in enumerate(row):
                if ch == "#":
                    self.g[y + dy, x + (3 - dx if mirrored else dx)] = WIRE

    def clock(self, y: int, x: int, h: int, w: int, start: int = 2) -> int:
        """A loop of wire with an electron in it, top-left corner at (y, x). Returns its period.

        start picks where the electron begins along the loop (clockwise from the top-left corner); neither
        its head nor its tail may sit on a corner, or a second electron sets off the other way round.
        Take the output from (y, x + w), carrying the top side on past the corner: a wire leaving the
        middle of a side touches the loop cell behind the electron too and sends a copy back round."""
        ring = ([(y, x + i) for i in range(w - 1)] + [(y + i, x + w - 1) for i in range(h - 1)]
                + [(y + h - 1, x + w - 1 - i) for i in range(w - 1)] + [(y + h - 1 - i, x) for i in range(h - 1)])
        corners = {(y, x), (y, x + w - 1), (y + h - 1, x), (y + h - 1, x + w - 1)}
        assert ring[start] not in corners and ring[start - 1] not in corners
        for c in ring:
            self.g[c] = WIRE
        self.g[ring[start]] = HEAD
        self.g[ring[start - 1]] = TAIL
        return len(ring) - 4   # an electron cuts every corner: the corner and the next cell fire together

    def trimmed(self) -> np.ndarray:
        rows, cols = np.flatnonzero(self.g.any(1)), np.flatnonzero(self.g.any(0))
        return self.g[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1].copy()


def heads(board: Board, probes: list[tuple[int, int]], steps: int = 600) -> list[list[int]]:
    """When an electron head passes each probe cell."""
    g = board.g.copy()
    out = np.zeros_like(g)
    times: list[list[int]] = [[] for _ in probes]
    for t in range(steps):
        _wire_step(g, out)
        g, out = out, g
        for i, probe in enumerate(probes):
            if g[probe] == HEAD:
                times[i].append(t)
    return times


def clocks() -> tuple[Board, bool]:
    b = Board(28, 60)
    ok = True
    for i, (h, w) in enumerate(((3, 4), (4, 4), (6, 6))):
        top = 1 + i * 9
        period = b.clock(top, 1, h, w)
        b.path((top, 1 + w), (top, 56))
        (times,) = heads(b, [(top, 50)])
        gaps = set(np.diff(times[2:]).tolist())
        ok &= gaps == {period}
        print(f"clock {period:2}: pulses every {sorted(gaps)}")
    return b, ok


def diodes() -> tuple[Board, bool]:
    b = Board(16, 50)
    b.clock(2, 1, 4, 5)
    b.path((2, 6), (2, 20))
    b.shape(DIODE, 2, 20)
    b.path((2, 24), (2, 46))
    b.clock(11, 1, 4, 5)
    b.path((11, 6), (11, 20))
    b.shape(DIODE, 11, 20, mirrored=True)
    b.path((11, 24), (11, 46))
    before, through, blocked = heads(b, [(2, 15), (2, 40), (11, 40)])
    ok = len(through) > 0 and set(np.diff(before[2:]).tolist()) == set(np.diff(through[2:]).tolist()) \
        and abs(len(before) - len(through)) <= 2 and not blocked
    print(f"diode: {len(before)} in, {len(through)} through, {len(blocked)} through the turned one")
    return b, ok


def gate(kind: str) -> tuple[Board, bool]:
    """Two clocks, periods 12 and 18 (both multiples of 6, so pulses meet exactly or not at all), into a gate.
    The second clock's electron start is tried along its loop until the pulses do meet now and then."""
    for start in range(2, 20):
        b = Board(26, 70)
        pa = b.clock(2, 2, 5, 5)             # period 12
        try:
            pb = b.clock(16, 2, 6, 7, start)  # period 18
        except AssertionError:
            continue
        r, x0 = 11, 32
        b.path((2, 7), (2, 26), (r - 2, 26), (r - 2, x0 - 1))
        b.path((16, 9), (16, 26), (r + 2, 26), (r + 2, x0 - 1))
        b.shape(XOR_GATE if kind == "xor" else OR_GATE, r, x0)
        b.path((r, x0 + 4 if kind == "xor" else x0 + 5), (r, 66))
        ta, tb, to = heads(b, [(r - 2, x0 - 3), (r + 2, x0 - 3), (r, 60)], steps=900)
        ta, tb = set(ta[3:]), set(tb[3:])
        if not ta & tb:
            continue   # the pulses never meet: not much of a demo
        ideal = ta ^ tb if kind == "xor" else ta | tb
        span = range(300, 800)
        got = [t for t in to if t in span]
        want: list[int] = []
        for lag in range(80):   # the wire from the gate to the probe delays everything the same
            want = sorted(t + lag for t in ideal if t + lag in span)
            if got == want:
                break
        ok = got == want
        print(f"{kind:3}: clocks {pa} and {pb}, {len(got)} pulses out over 500 steps, ideal gate {len(want)}"
              f" -> {'exact' if ok else 'WRONG'}")
        return b, ok
    print(f"{kind}: no electron start makes the pulses meet")
    return Board(1, 1), False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.rle"):
        old.unlink()
    results = []
    for stem, build, comment in (
        ("01 Basics - Clocks", clocks,
         "Loops of wire with an electron inside tick at their own period: 6, 8 and 16 steps, one pulse per "
         "lap down each wire. An electron cuts every corner, so a loop's period is its length minus four."),
        ("02 Basics - Diodes", diodes,
         "The same clock twice. The top diode lets its electrons through; the bottom one is turned around "
         "and stops them."),
        ("03 Gates - OR gate", lambda: gate("or"),
         "Clocks of period 12 and 18 into an OR gate: a pulse comes out when either input sends one, and one "
         "pulse when both arrive together."),
        ("04 Gates - XOR gate", lambda: gate("xor"),
         "The same two clocks into an XOR gate: a pulse comes out when exactly one input sends one. Every "
         "36 steps both arrive together and cancel out."),
    ):
        board, ok = build()
        results.append(ok)
        name = stem.split(" - ", 1)[1]
        pattern = Pattern(name, Wireworld(), board.trimmed(), comments=(comment,))
        (OUT / f"{stem}.rle").write_text(to_rle(pattern), encoding="utf-8")
    print("all circuits work" if all(results) else "SOME CIRCUITS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
