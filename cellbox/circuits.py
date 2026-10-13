"""Random Wireworld circuits for a reseed: clock loops with electrons in them, and wires that wander off
the loops, turn, and run into other wires. Electrons leave every loop through its wires, spread at the
junctions, and meet head-on and cancel out, so the board keeps flickering.

Two things keep it from filling up with electrons until every wire just hums:

- Every wire leaves its loop through a diode, from a corner, carrying one side of the loop straight on.
  A T-junction sends a copy of each electron back the way it came; without the diode those copies would
  get into the loop, which keeps them for ever and fills up.
- A wire stops short of other loops and diodes instead of joining them, for the same reason, and it never joins a
  network it is already part of: the wires form trees, and an electron has no cycle to run round in.

Wires never run alongside each other: a wire that comes next to another one joins it and ends there,
which keeps every wire one cell thick (thick wires short-circuit into noise).
"""

import numpy as np

from cellbox.rules import Wireworld

EMPTY, HEAD, TAIL, WIRE = Wireworld.EMPTY, Wireworld.HEAD, Wireworld.TAIL, Wireworld.WIRE

LOOP_SIDE = (6, 22)        # loop width and height, cells
LOOP_AREA = 800            # field cells per loop at density 1

# The diode (found by brute-force search, see tools/make_circuits.py; it holds against electrons coming
# back at any period and phase) along a wire heading in direction d, as (steps along d from the loop
# corner, steps to the side). The wire itself is empty for steps 3 to 5.
DIODE_CELLS = ((1, 0), (2, 0), (6, 0)) + tuple((s, k) for s in (2, 3, 4, 5) for k in (-1, 1))     + tuple((s, k) for s in (3, 4) for k in (-2, 2))
DIODE_GAP = ((3, 0), (4, 0), (5, 0))
DIODE_LENGTH = 6


def _ring(y: int, x: int, h: int, w: int) -> list[tuple[int, int]]:
    """The cells of a rectangle's outline, clockwise from the top-left corner."""
    cells = [(y, x + i) for i in range(w - 1)]
    cells += [(y + i, x + w - 1) for i in range(h - 1)]
    cells += [(y + h - 1, x + w - 1 - i) for i in range(w - 1)]
    cells += [(y + h - 1 - i, x) for i in range(h - 1)]
    return cells


def _neighbors(y: int, x: int) -> list[tuple[int, int]]:
    return [(y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def generate(n: int, density: float, spot: bool, rng: np.random.Generator) -> np.ndarray:
    grid = np.zeros((n, n), dtype=np.uint8)
    if spot:
        side = max(48, int(n * 0.4))
        lo, hi = (n - side) // 2, (n + side) // 2
    else:
        lo, hi = 0, n
    loops = max(1, round(density * (hi - lo) ** 2 / LOOP_AREA))

    rings: list[list[tuple[int, int]]] = []
    for _ in range(loops * 20):
        if len(rings) >= loops:
            break
        h, w = (int(v) for v in rng.integers(*LOOP_SIDE, size=2))
        if hi - lo <= max(h, w) + 2 * DIODE_LENGTH:
            continue
        y = int(rng.integers(lo + DIODE_LENGTH, hi - h - DIODE_LENGTH))
        x = int(rng.integers(lo + DIODE_LENGTH, hi - w - DIODE_LENGTH))
        if grid[y - 4:y + h + 4, x - 4:x + w + 4].any():
            continue   # keep loops apart
        ring = _ring(y, x, h, w)
        for c in ring:
            grid[c] = WIRE
        # an electron must not sit on a corner, or a second one sets off the other way round
        corners = {(y, x), (y, x + w - 1), (y + h - 1, x), (y + h - 1, x + w - 1)}
        spots = [i for i in range(len(ring)) if ring[i] not in corners and ring[i - 1] not in corners]
        electrons = int(rng.integers(1, 4))
        for k in range(electrons):
            i = spots[(int(rng.integers(len(spots))) + k * len(spots) // electrons) % len(spots)]
            grid[ring[i]] = HEAD
            grid[ring[i - 1]] = TAIL
        rings.append(ring)

    loop_cells = {c for ring in rings for c in ring}
    nets = Networks(n)
    for ring in rings:
        for _ in range(rng.integers(1, 4)):
            _wander(grid, ring, loop_cells, nets, rng, lo, hi)
    return grid


class Networks:
    """Which wire cells are connected (union-find over wires; loops are not part of any)."""

    def __init__(self, n: int):
        self.cell = np.full((n, n), -1, dtype=np.int64)
        self.parent: list[int] = []

    def new(self) -> int:
        self.parent.append(len(self.parent))
        return self.parent[-1]

    def root(self, net: int) -> int:
        while self.parent[net] != net:
            self.parent[net] = self.parent[self.parent[net]]
            net = self.parent[net]
        return net

    def join(self, a: int, b: int) -> None:
        self.parent[self.root(a)] = self.root(b)


def _wander(grid: np.ndarray, ring: list[tuple[int, int]], loop_cells: set, nets: Networks,
            rng: np.random.Generator, lo: int, hi: int) -> None:
    """A wire out of a loop corner through a diode, turning now and then, until it joins a wire or ends."""
    ys = [c[0] for c in ring]
    xs = [c[1] for c in ring]
    top, bottom, left, right = min(ys), max(ys), min(xs), max(xs)
    # electrons run clockwise, so the wire carries on the way they come into the corner; one that carried
    # on the other side would touch the cell they turn into and send copies back into the loop
    corner, d = (((top, left), (-1, 0)), ((top, right), (0, 1)), ((bottom, right), (1, 0)),
                 ((bottom, left), (0, -1)))[rng.integers(4)]
    dy, dx = d
    py, px = dx, dy   # sideways
    cells = [(corner[0] + s * dy + k * py, corner[1] + s * dx + k * px) for s, k in DIODE_CELLS]
    gap = [(corner[0] + s * dy, corner[1] + s * dx) for s, _ in DIODE_GAP]
    exit_cell = cells[2]
    footprint = set(cells + gap)
    around = {nb for c in footprint for nb in _neighbors(*c)} - footprint - set(_neighbors(*corner)) - {corner}
    if any(not (lo <= y < hi and lo <= x < hi) for y, x in footprint | around | {corner}):
        return
    if any(grid[c] != EMPTY for c in footprint | around):
        return   # no room for the diode here
    net = nets.new()
    for c in cells:
        grid[c] = WIRE
        nets.cell[c] = net
    loop_cells.update(c for c in cells if c != exit_cell)   # a wire joining the diode would get round it

    prev = exit_cell
    near = footprint   # the diode's own cells do not count as another wire
    length = int(rng.integers(30, 220))
    run = int(rng.integers(4, 30))
    for _ in range(length):
        if run == 0:
            dy, dx = d
            d = (dx, -dy) if rng.random() < 0.5 else (-dx, dy)
            run = int(rng.integers(4, 40))
        cell = (prev[0] + d[0], prev[1] + d[1])
        if not (lo < cell[0] < hi - 1 and lo < cell[1] < hi - 1) or grid[cell] != EMPTY:
            return   # the edge (one cell in, so neighbors stay on the grid) or a wire
        allowed = set(_neighbors(*prev)) | {prev} | near
        touched = [c for c in _neighbors(*cell) if grid[c] != EMPTY and c not in allowed]
        if any(c in loop_cells for c in touched):
            return   # stop short of a loop: joining it would feed it electrons
        others = {nets.root(int(nets.cell[c])) for c in touched}
        if nets.root(net) in others:
            return   # stop short of its own network: that would close a cycle
        grid[cell] = WIRE
        nets.cell[cell] = net
        if touched:
            for other in others:
                nets.join(other, net)
            return   # came next to another wire: this cell joins them
        near = set()
        prev = cell
        run -= 1
