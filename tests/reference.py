"""A straightforward numpy implementation of one step: the yardstick for the numba kernel."""

import numpy as np

from cellbox.rules import Rule


def step(state: np.ndarray, age: np.ndarray, rule: Rule) -> tuple[np.ndarray, np.ndarray]:
    alive = state == 1
    n = sum(np.roll(np.roll(alive, dy, 0), dx, 1).astype(np.int64)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    born = (state == 0) & np.isin(n, list(rule.birth))
    stays = alive & np.isin(n, list(rule.survive))
    dies = alive & ~stays
    dying = state >= 2

    new_state = np.zeros_like(state)
    new_state[born | stays] = 1
    if rule.is_generations:
        new_state[dies] = 2
        fading = state.astype(np.int64) + 1
        new_state[dying] = np.where(fading[dying] < rule.states, fading[dying], 0)

    new_age = np.zeros_like(age)
    new_age[born] = 1
    new_age[stays] = np.minimum(age[stays].astype(np.int64) + 1, 255)
    return new_state, new_age
