"""Random Wireworld circuits for a reseed: clock loops with electrons in them, and wires that wander off
the loops, turn, and join other wires. Electrons leave every loop through its wires, meet at the
junctions and either merge, cancel or feed new loops, so the board keeps flickering.

Wires never run alongside each other: a wire that comes next to another one joins it and ends there,
which keeps every wire one cell thick (thick wires short-circuit into noise).
"""

import numpy as np

from cellbox.rules import Wireworld

EMPTY, HEAD, TAIL, WIRE = Wireworld.EMPTY, Wireworld.HEAD, Wireworld.TAIL, Wireworld.WIRE

LOOP_SIDE = (6, 22)        # loop width and height, cells
LOOP_AREA = 2400           # field cells per loop at density 1 / 0.3 ... roughly
DIRS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def _ring(y: int, x: int, h: int, w: int) -> list[tuple[int, int]]:
    """The cells of a rectangle's outline, clockwise from the top-left corner."""
    cells = [(y, x + i) for i in range(w - 1)]
    cells += [(y + i, x + w - 1) for i in range(h - 1)]
    cells += [(y + h - 1, x + w - 1 - i) for i in range(w - 1)]
    cells += [(y + h - 1 - i, x) for i in range(h - 1)]
    return cells


def _neighbors(y: int, x: int, n: int) -> list[tuple[int, int]]:
    return [((y + dy) % n, (x + dx) % n) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def generate(n: int, density: float, spot: bool, rng: np.random.Generator) -> np.ndarray:
    grid = np.zeros((n, n), dtype=np.uint8)
    if spot:
        side = max(48, int(n * 0.4))
        lo, hi = (n - side) // 2, (n + side) // 2
    else:
        lo, hi = 0, n
    area = (hi - lo) ** 2
    loops = max(1, round(density * area / LOOP_AREA * 3))

    rings: list[list[tuple[int, int]]] = []
    for _ in range(loops * 20):
        if len(rings) >= loops:
            break
        h, w = rng.integers(*LOOP_SIDE, size=2)
        if hi - lo <= max(h, w) + 4:
            continue
        y, x = rng.integers(lo, hi - h), rng.integers(lo, hi - w)
        if grid[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3].any():
            continue   # keep loops apart
        ring = _ring(int(y), int(x), int(h), int(w))
        for cy, cx in ring:
            grid[cy, cx] = WIRE
        # an electron must not sit on a corner, or a second one sets off the other way round
        corners = {(int(y), int(x)), (int(y), int(x + w - 1)), (int(y + h - 1), int(x)),
                   (int(y + h - 1), int(x + w - 1))}
        spots = [i for i in range(len(ring)) if ring[i] not in corners and ring[i - 1] not in corners]
        electrons = int(rng.integers(1, 4))
        for k in range(electrons):
            i = spots[(int(rng.integers(len(spots))) + k * len(spots) // electrons) % len(spots)]
            grid[ring[i]] = HEAD
            grid[ring[i - 1]] = TAIL
        rings.append(ring)

    for ring in rings:
        for _ in range(rng.integers(1, 4)):
            _wander(grid, ring, rng, lo, hi)
    return grid


def _wander(grid: np.ndarray, ring: list[tuple[int, int]], rng: np.random.Generator, lo: int, hi: int) -> None:
    """A wire from a point on the loop outwards, turning now and then, until it joins something or ends."""
    n = grid.shape[0]
    ys = [c[0] for c in ring]
    xs = [c[1] for c in ring]
    top, bottom, left, right = min(ys), max(ys), min(xs), max(xs)
    # start in the middle of a side, never at a corner, heading straight out
    side = rng.integers(4)
    if side == 0:
        start, d = (top, int(rng.integers(left + 1, right))), (-1, 0)
    elif side == 1:
        start, d = (int(rng.integers(top + 1, bottom)), right), (0, 1)
    elif side == 2:
        start, d = (bottom, int(rng.integers(left + 1, right))), (1, 0)
    else:
        start, d = (int(rng.integers(top + 1, bottom)), left), (0, -1)
    if grid[start] != WIRE:
        return   # an electron sits there right now; skip this branch
    near_loop = set(_neighbors(*start, n)) | {start}
    prev = start
    length = int(rng.integers(30, 220))
    run = int(rng.integers(4, 30))
    for _ in range(length):
        if run == 0:
            dy, dx = d
            d = (dx, -dy) if rng.random() < 0.5 else (-dx, dy)
            run = int(rng.integers(4, 40))
        cell = ((prev[0] + d[0]) % n, (prev[1] + d[1]) % n)
        if not (lo <= cell[0] < hi and lo <= cell[1] < hi):
            return
        if grid[cell] != EMPTY:
            return   # ran into a wire: joined
        allowed = set(_neighbors(*prev, n)) | {prev} | near_loop
        touching = any(grid[c] != EMPTY and c not in allowed for c in _neighbors(*cell, n))
        grid[cell] = WIRE
        if touching:
            return   # came next to another wire: this cell joins them
        near_loop = set()
        prev = cell
        run -= 1
