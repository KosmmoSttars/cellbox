"""The simulation: a toroidal grid stepped by one of three kernels.

Life-like and Generations rules: cell states 0 = dead, 1 = alive, 2..C-1 = dying (each step a dying cell
moves one state closer to dead). Alongside the states the field keeps each live cell's age in steps,
capped at 255, which the view turns into color.

Wireworld: states 0 empty, 1 electron head, 2 electron tail, 3 wire.

Lenia: every cell holds a float from 0 to 1. A step convolves the field with a ring-shaped kernel (by FFT,
since the kernel is dozens of cells across), maps that through a growth bell curve and adds 1/T of it.
The view gets the values quantized to 0..255.

Import cellbox.jitcache and call install() before importing this module (main.py does).
"""

import numpy as np
from numba import njit

from cellbox.rules import DEFAULT_RULE, AnyRule, LeniaRule, Rule, Wireworld

AGE_CAP = 255
SIZES = (128, 256, 512, 1024)
DEFAULT_SIZE = 256

SPOT_FRACTION = 0.25   # "center spot" seeding: a disc this share of the field side across


@njit("int64(uint8[:, ::1], uint8[:, ::1], uint8[:, ::1], uint8[:, ::1], boolean[::1], boolean[::1], int64)",
      cache=True, nogil=True)
def _step(state, age, out_state, out_age, birth, survive, states):
    """One Life-like or Generations step on a torus. Writes into out_*; returns the number of live cells."""
    h, w = state.shape
    population = 0
    for y in range(h):
        up = y - 1 if y > 0 else h - 1
        down = y + 1 if y < h - 1 else 0
        for x in range(w):
            left = x - 1 if x > 0 else w - 1
            right = x + 1 if x < w - 1 else 0
            n = ((state[up, left] == 1) + (state[up, x] == 1) + (state[up, right] == 1)
                 + (state[y, left] == 1) + (state[y, right] == 1)
                 + (state[down, left] == 1) + (state[down, x] == 1) + (state[down, right] == 1))
            s = state[y, x]
            if s == 0:
                if birth[n]:
                    out_state[y, x] = 1
                    out_age[y, x] = 1
                    population += 1
                else:
                    out_state[y, x] = 0
                    out_age[y, x] = 0
            elif s == 1:
                if survive[n]:
                    out_state[y, x] = 1
                    a = age[y, x]
                    out_age[y, x] = a + 1 if a < 255 else 255
                    population += 1
                else:
                    out_state[y, x] = 2 if states > 2 else 0
                    out_age[y, x] = 0
            else:
                out_state[y, x] = s + 1 if s + 1 < states else 0
                out_age[y, x] = 0
    return population


@njit("int64(uint8[:, ::1], uint8[:, ::1])", cache=True, nogil=True)
def _wire_step(state, out):
    """One Wireworld step on a torus. Returns the number of electron heads."""
    h, w = state.shape
    heads = 0
    for y in range(h):
        up = y - 1 if y > 0 else h - 1
        down = y + 1 if y < h - 1 else 0
        for x in range(w):
            s = state[y, x]
            if s == 3:
                left = x - 1 if x > 0 else w - 1
                right = x + 1 if x < w - 1 else 0
                n = ((state[up, left] == 1) + (state[up, x] == 1) + (state[up, right] == 1)
                     + (state[y, left] == 1) + (state[y, right] == 1)
                     + (state[down, left] == 1) + (state[down, x] == 1) + (state[down, right] == 1))
                if n == 1 or n == 2:
                    out[y, x] = 1
                    heads += 1
                else:
                    out[y, x] = 3
            elif s == 1:
                out[y, x] = 2
            elif s == 2:
                out[y, x] = 3
            else:
                out[y, x] = 0
    return heads


@njit("float64(float32[:, ::1], float32[:, ::1], uint8[:, ::1], float64, float64, float64)",
      cache=True, nogil=True)
def _lenia_grow(cells, potential, shown, mu, sigma, dt):
    """cells += dt * growth(potential), clipped to 0..1; refreshes the 8-bit view. Returns the total mass."""
    h, w = cells.shape
    inv = 1.0 / (9.0 * sigma * sigma)
    mass = 0.0
    for y in range(h):
        for x in range(w):
            d = potential[y, x] - mu
            g = 1.0 - d * d * inv
            g = g * g * g * g * 2.0 - 1.0 if g > 0.0 else -1.0
            v = cells[y, x] + dt * g
            v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
            cells[y, x] = v
            shown[y, x] = np.uint8(v * 255.0 + 0.5)
            mass += v
    return mass


def neighbor_mask(counts: frozenset[int]) -> np.ndarray:
    mask = np.zeros(9, dtype=np.bool_)
    mask[list(counts)] = True
    return mask


def lenia_kernel(size: int, rule: LeniaRule) -> np.ndarray:
    """The normalized kernel on a size x size torus, centered on cell (0, 0)."""
    i = np.arange(size)
    d = np.minimum(i, size - i).astype(np.float64)
    r = np.sqrt(d[:, None] ** 2 + d[None, :] ** 2) / rule.radius
    rings = len(rule.peaks)
    br = rings * r
    peaks = np.array([float(p) for p in rule.peaks])
    height = peaks[np.minimum(np.floor(br).astype(int), rings - 1)]
    t = np.minimum(br % 1.0, 1.0)
    core = (4.0 * t * (1.0 - t)) ** 4
    kernel = np.where(r < 1.0, core * height, 0.0)
    return (kernel / kernel.sum()).astype(np.float32)


class Field:
    def __init__(self, size: int = DEFAULT_SIZE, rule: AnyRule = DEFAULT_RULE):
        self._rule = rule
        self.resize(size)
        self.rule = rule

    @property
    def size(self) -> int:
        return self.state.shape[0]

    @property
    def rule(self) -> AnyRule:
        return self._rule

    @rule.setter
    def rule(self, rule: AnyRule) -> None:
        """Takes effect on the next step. Within a family the cells stay as they are; a new family
        starts from an empty field."""
        family_changed = rule.family != self._rule.family
        self._rule = rule
        if isinstance(rule, Rule):
            self._birth = neighbor_mask(rule.birth)
            self._survive = neighbor_mask(rule.survive)
        self._kernel_fft = None
        if family_changed:
            self.clear()

    @property
    def is_continuous(self) -> bool:
        return isinstance(self._rule, LeniaRule)

    def resize(self, size: int) -> None:
        """A new, empty field."""
        self.state = np.zeros((size, size), dtype=np.uint8)
        self.age = np.zeros_like(self.state)
        self._spare_state = np.zeros_like(self.state)
        self._spare_age = np.zeros_like(self.state)
        self.cells = np.zeros((size, size), dtype=np.float32)   # Lenia values
        self._shown = np.zeros_like(self.state)                 # ...and how the view sees them
        self._kernel_fft = None
        self.generation = 0
        self.population = 0   # live cells, electron heads, or Lenia's total mass

    def clear(self) -> None:
        self.resize(self.size)

    # --- seeding ----------------------------------------------------------------------------

    def _zone(self, rng: np.random.Generator, density: float, spot: bool) -> np.ndarray:
        n = self.size
        alive = rng.random((n, n)) < density
        if spot:
            yy, xx = np.ogrid[:n, :n]
            r = n * SPOT_FRACTION / 2
            c = (n - 1) / 2
            alive &= (yy - c) ** 2 + (xx - c) ** 2 <= r * r
        return alive

    def seed(self, density: float, spot: bool, seed: int, species: np.ndarray | None = None) -> None:
        """A random start. density (0..1) is the share of live cells in the seeded zone for Life-like rules,
        and how crowded the field gets for Wireworld circuits and Lenia creatures. For Lenia, species is a
        creature to scatter around; without one the field gets patches of noise."""
        rng = np.random.default_rng(seed)
        self.clear()
        if isinstance(self._rule, Wireworld):
            from cellbox.circuits import generate
            self.state = generate(self.size, density, spot, rng)
        elif isinstance(self._rule, LeniaRule):
            self._seed_lenia(rng, density, spot, species)
        else:
            alive = self._zone(rng, density, spot)
            self.state = alive.astype(np.uint8)
            self.age = self.state.copy()
        self._recount()

    def _seed_lenia(self, rng: np.random.Generator, density: float, spot: bool,
                    species: np.ndarray | None) -> None:
        n, radius = self.size, self._rule.radius
        if species is not None:
            h, w = species.shape
            if spot:
                count = 1 + round(density * 3)
                center, spread = n / 2, n * SPOT_FRACTION / 2
            else:
                count = max(1, round(density * n * n / (h * w * 8)))
                center, spread = n / 2, n / 2
            for _ in range(count):
                shape = np.rot90(species, rng.integers(4))
                if rng.random() < 0.5:
                    shape = shape[:, ::-1]
                y, x = (center + rng.uniform(-spread, spread, 2)).astype(int)
                self.stamp(np.ascontiguousarray(shape), y - shape.shape[0] // 2, x - shape.shape[1] // 2,
                           overwrite=False)
            return
        side = 3 * radius
        if spot:
            boxes = [(n // 2 - side, n // 2 - side, 2 * side)]
        else:
            count = max(1, round(density * (n / (2.5 * side)) ** 2))
            boxes = [(*rng.integers(0, n, 2), side) for _ in range(count)]
        for y, x, s in boxes:
            patch = rng.random((s, s)).astype(np.float32)
            self.stamp(patch, int(y), int(x), overwrite=False)

    # --- patterns ---------------------------------------------------------------------------

    def stamp(self, cells: np.ndarray, y: int, x: int, overwrite: bool = True) -> None:
        """Places a pattern with its top-left corner at (y, x), wrapping around the torus.
        overwrite clears the pattern's whole box first; otherwise only its non-empty cells land
        (for Lenia the larger value wins)."""
        h, w = cells.shape
        n = self.size
        if h > n or w > n:
            raise ValueError(f"A {w} x {h} pattern does not fit a {n} x {n} field.")
        ys = (np.arange(h) + y) % n
        xs = (np.arange(w) + x) % n
        box = np.ix_(ys, xs)
        if self.is_continuous:
            values = cells.astype(np.float32)
            self.cells[box] = values if overwrite else np.maximum(self.cells[box], values)
        else:
            states = cells.astype(np.uint8)
            if overwrite:
                self.state[box] = states
                self.age[box] = states == 1
            else:
                mask = states != 0
                target_state, target_age = self.state[box], self.age[box]
                target_state[mask] = states[mask]
                target_age[mask] = states[mask] == 1
                self.state[box], self.age[box] = target_state, target_age
        self._recount()

    def extract(self) -> np.ndarray | None:
        """The bounding box of everything that is not empty, or None for an empty field."""
        data = self.cells if self.is_continuous else self.state
        filled = data > (1 / 255 if self.is_continuous else 0)
        rows, cols = np.flatnonzero(filled.any(1)), np.flatnonzero(filled.any(0))
        if not len(rows):
            return None
        return data[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1].copy()

    def _recount(self) -> None:
        if self.is_continuous:
            self._shown = np.rint(self.cells * 255).astype(np.uint8)
            self.population = float(self.cells.sum(dtype=np.float64))
        elif isinstance(self._rule, Wireworld):
            self.population = int((self.state == Wireworld.HEAD).sum())
        else:
            self.population = int((self.state == 1).sum())

    # --- stepping ---------------------------------------------------------------------------

    def step(self, count: int = 1) -> None:
        rule = self._rule
        for _ in range(count):
            if isinstance(rule, LeniaRule):
                if self._kernel_fft is None:
                    self._kernel_fft = np.fft.rfft2(lenia_kernel(self.size, rule))
                potential = np.fft.irfft2(np.fft.rfft2(self.cells) * self._kernel_fft, s=self.cells.shape)
                self.population = _lenia_grow(self.cells, np.ascontiguousarray(potential, dtype=np.float32),
                                              self._shown, rule.mu, rule.sigma, 1.0 / rule.period)
            elif isinstance(rule, Wireworld):
                self.population = _wire_step(self.state, self._spare_state)
                self.state, self._spare_state = self._spare_state, self.state
            else:
                self.population = _step(self.state, self.age, self._spare_state, self._spare_age,
                                        self._birth, self._survive, rule.states)
                self.state, self._spare_state = self._spare_state, self.state
                self.age, self._spare_age = self._spare_age, self.age
            self.generation += 1

    def display(self) -> np.ndarray:
        """What the view colors: ages for Life-like rules, states for Generations and Wireworld,
        quantized values for Lenia."""
        if self.is_continuous:
            return self._shown
        return self.age if isinstance(self._rule, Rule) and not self._rule.is_generations else self.state


def warm_up() -> None:
    """Runs the kernels once so the first real step does not pause (loads them from cache or compiles)."""
    from cellbox.rules import parse
    Field(8).step()
    Field(8, Wireworld()).step()
    Field(32, parse("Lenia R=4 T=10 m=0.15 s=0.015 b=1")).step()
