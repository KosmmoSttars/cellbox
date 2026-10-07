"""The simulation: a toroidal grid of cell states, stepped by a numba kernel.

Cell states: 0 = dead, 1 = alive, 2..C-1 = dying (Generations rules only; each step a dying cell
moves one state closer to dead). Alongside the states the field keeps each live cell's age in steps,
capped at 255, which the view turns into color.

Import cellbox.jitcache and call install() before importing this module (main.py does).
"""

import numpy as np
from numba import njit

from cellbox.rules import DEFAULT_RULE, Rule

AGE_CAP = 255
SIZES = (128, 256, 512, 1024)
DEFAULT_SIZE = 256

SPOT_FRACTION = 0.25   # "center spot" seeding: a disc this share of the field side across


@njit("int64(uint8[:, ::1], uint8[:, ::1], uint8[:, ::1], uint8[:, ::1], boolean[::1], boolean[::1], int64)",
      cache=True, nogil=True)
def _step(state, age, out_state, out_age, birth, survive, states):
    """One generation on a torus. Writes into out_*; returns the number of live cells."""
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


def neighbor_mask(counts: frozenset[int]) -> np.ndarray:
    mask = np.zeros(9, dtype=np.bool_)
    mask[list(counts)] = True
    return mask


class Field:
    def __init__(self, size: int = DEFAULT_SIZE, rule: Rule = DEFAULT_RULE):
        self.rule = rule
        self.resize(size)

    @property
    def size(self) -> int:
        return self.state.shape[0]

    @property
    def rule(self) -> Rule:
        return self._rule

    @rule.setter
    def rule(self, rule: Rule) -> None:
        """Takes effect on the next step; the cells stay as they are."""
        self._rule = rule
        self._birth = neighbor_mask(rule.birth)
        self._survive = neighbor_mask(rule.survive)

    def resize(self, size: int) -> None:
        """A new, empty field."""
        self.state = np.zeros((size, size), dtype=np.uint8)
        self.age = np.zeros_like(self.state)
        self._spare_state = np.zeros_like(self.state)
        self._spare_age = np.zeros_like(self.state)
        self.generation = 0
        self.population = 0

    def clear(self) -> None:
        self.resize(self.size)

    def seed(self, density: float, spot: bool, seed: int) -> None:
        """Random live cells. density is the share of live cells inside the seeded zone (0..1)."""
        n = self.size
        rng = np.random.default_rng(seed)
        alive = rng.random((n, n)) < density
        if spot:
            yy, xx = np.ogrid[:n, :n]
            r = n * SPOT_FRACTION / 2
            c = (n - 1) / 2
            alive &= (yy - c) ** 2 + (xx - c) ** 2 <= r * r
        self.state = alive.astype(np.uint8)
        self.age = self.state.copy()
        self.generation = 0
        self.population = int(alive.sum())

    def step(self, count: int = 1) -> None:
        for _ in range(count):
            self.population = _step(self.state, self.age, self._spare_state, self._spare_age,
                                    self._birth, self._survive, self._rule.states)
            self.state, self._spare_state = self._spare_state, self.state
            self.age, self._spare_age = self._spare_age, self.age
            self.generation += 1

    def display(self) -> np.ndarray:
        """What the view colors: ages for Life-like rules, states for Generations."""
        return self.state if self._rule.is_generations else self.age


def warm_up() -> None:
    """Runs the kernel once so the first real step does not pause (loads it from cache or compiles)."""
    Field(8).step()
