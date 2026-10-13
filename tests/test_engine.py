import numpy as np
import pytest

from cellbox.engine import Field
from cellbox.rules import PRESETS, parse
from tests import reference

GLIDER = ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2))


def field_with(cells, size=16, rule="B3/S23") -> Field:
    field = Field(size, parse(rule))
    for y, x in cells:
        field.state[y, x] = 1
        field.age[y, x] = 1
    return field


def test_glider_wraps_around_the_torus():
    field = field_with(GLIDER)
    start = field.state.copy()
    field.step(4)   # one glider period: same shape, one cell down and right
    assert np.array_equal(field.state, np.roll(start, (1, 1), (0, 1)))
    field.step(4 * 15)   # 16 periods in total: all the way around a 16-cell torus
    assert np.array_equal(field.state, start)
    assert field.generation == 64
    assert field.population == 5


def test_blinker_oscillates():
    field = field_with(((5, 4), (5, 5), (5, 6)))
    start = field.state.copy()
    field.step()
    assert not np.array_equal(field.state, start)
    assert field.state[4:7, 5].tolist() == [1, 1, 1]
    field.step()
    assert np.array_equal(field.state, start)


def test_block_ages_and_caps():
    field = field_with(((3, 3), (3, 4), (4, 3), (4, 4)))
    field.step(10)
    assert field.age[3, 3] == 11
    field.step(300)
    assert field.age[3, 3] == 255
    assert field.age.sum() == 4 * 255


def test_brians_brain_cells_fade():
    field = field_with(((5, 5),), rule="B2/S/C3")
    field.step()
    assert field.state[5, 5] == 2   # alive -> dying
    field.step()
    assert field.state[5, 5] == 0   # dying -> dead


def test_switching_to_life_like_drops_dying_cells():
    field = field_with(((5, 5),), rule="B2/S/C3")
    field.step()
    field.rule = parse("B3/S23")
    field.step()
    assert field.state.max() == 0


@pytest.mark.parametrize("preset", [p for p in PRESETS if p.rule.family == "life"], ids=lambda p: p.name)
def test_kernel_matches_numpy_reference(preset):
    field = Field(64, preset.rule)
    field.seed(0.35, spot=False, seed=7)
    state, age = field.state.copy(), field.age.copy()
    for _ in range(40):
        field.step()
        state, age = reference.step(state, age, preset.rule)
        assert np.array_equal(field.state, state)
        assert np.array_equal(field.age, age)
    assert field.population == int((state == 1).sum())


def test_seed_is_repeatable_and_respects_density():
    a, b = Field(256), Field(256)
    a.seed(0.3, spot=False, seed=42)
    b.seed(0.3, spot=False, seed=42)
    assert np.array_equal(a.state, b.state)
    assert 0.28 < a.population / 256 ** 2 < 0.32


def test_spot_seed_stays_in_the_center():
    field = Field(128)
    field.seed(1.0, spot=True, seed=1)
    assert field.state[64, 64] == 1
    assert field.state[0, 0] == 0 and field.state[64, 10] == 0
