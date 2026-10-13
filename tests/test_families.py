"""Wireworld, Lenia, RLE and the pattern library."""

from fractions import Fraction

import numpy as np
import pytest

from cellbox.circuits import generate
from cellbox.engine import Field, lenia_kernel
from cellbox.patterns import Pattern, PatternError, library, parse_rle, species, to_rle
from cellbox.rules import LeniaRule, PRESETS, RuleError, Wireworld, parse, preset_name


# --- rules ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["WireWorld", "wireworld", "Wire-World"])
def test_wireworld_spellings(text):
    assert parse(text) == Wireworld()


def test_lenia_parses_and_round_trips():
    rule = parse("Lenia R=18 T=10 m=0.24 s=0.029 b=1;1/3")
    assert rule == LeniaRule(18, 10, 0.24, 0.029, (Fraction(1), Fraction(1, 3)))
    assert parse(str(rule)) == rule
    assert parse("lenia r13 t10 m0.15 s0.015") == LeniaRule()
    assert parse("Lenia R=10 T=10 m=0.27 s=0.044 b=1/2,1").peaks == (Fraction(1, 2), Fraction(1))


@pytest.mark.parametrize("text", ["Lenia", "Lenia R=13 T=10 m=0.15", "Lenia R=1 T=10 m=0.15 s=0.01",
                                  "Lenia R=13 T=10 m=1.5 s=0.01", "Lenia R=13 T=10 m=0.1 s=0.01 b=0",
                                  "Lenia R=13 T=10 m=0.1 s=0.01 b=1;1;1;1;1"])
def test_bad_lenia_rules(text):
    with pytest.raises(RuleError):
        parse(text)


def test_every_preset_round_trips():
    for preset in PRESETS:
        assert parse(str(preset.rule)) == preset.rule
        assert preset_name(preset.rule) == preset.name


def test_lenia_presets_have_their_creatures():
    for preset in PRESETS:
        if preset.species:
            creature = species(preset.species)
            assert creature is not None and creature.rule == preset.rule


# --- Wireworld ------------------------------------------------------------------------------------

def wire_reference(state: np.ndarray) -> np.ndarray:
    heads = (state == 1).astype(np.int64)
    n = sum(np.roll(np.roll(heads, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    out = state.copy()
    out[state == 1] = 2
    out[state == 2] = 3
    out[(state == 3) & ((n == 1) | (n == 2))] = 1
    return out


def test_wireworld_kernel_matches_reference():
    field = Field(128, Wireworld())
    field.seed(0.6, spot=False, seed=3)
    state = field.state.copy()
    assert (state == 1).any() and (state == 3).any()
    for _ in range(60):
        field.step()
        state = wire_reference(state)
        assert np.array_equal(field.state, state)
    assert field.population == int((state == 1).sum())


def test_random_circuits_are_repeatable_and_keep_wires_thin():
    a = generate(256, 0.3, False, np.random.default_rng(5))
    b = generate(256, 0.3, False, np.random.default_rng(5))
    assert np.array_equal(a, b)
    filled = a != 0
    blocks = filled[:-1, :-1] & filled[1:, :-1] & filled[:-1, 1:] & filled[1:, 1:]
    assert blocks.sum() < 0.03 * filled.sum()   # wires do not run side by side (each diode has two blocks)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_random_circuits_never_fill_up(seed):
    """Diodes keep electrons that come back from junctions out of the loops: without them every wire
    ends up humming with an electron every third cell."""
    field = Field(256, Wireworld())
    field.seed(1.0, spot=False, seed=seed)
    field.step(2000)
    assert 0 < field.population < 0.12 * (field.state != 0).sum()


def test_spot_circuit_stays_in_the_middle():
    grid = generate(256, 0.5, True, np.random.default_rng(1))
    assert grid.any()
    assert not grid[:40].any() and not grid[-40:].any()


# --- Lenia ----------------------------------------------------------------------------------------

def lenia_reference(cells: np.ndarray, rule: LeniaRule) -> np.ndarray:
    kernel = lenia_kernel(cells.shape[0], rule).astype(np.float64)
    potential = np.real(np.fft.ifft2(np.fft.fft2(cells.astype(np.float64)) * np.fft.fft2(kernel)))
    growth = np.maximum(0, 1 - (potential - rule.mu) ** 2 / (9 * rule.sigma ** 2)) ** 4 * 2 - 1
    return np.clip(cells + growth / rule.period, 0, 1)


def test_lenia_kernel_is_a_normalized_ring():
    rule = parse("Lenia R=13 T=10 m=0.15 s=0.015 b=1")
    k = lenia_kernel(64, rule)
    assert abs(k.sum() - 1) < 1e-5
    assert k[0, 0] == 0                    # the center is not its own neighbor
    assert k[0, 13] == 0 and k[0, 7] > 0   # nothing at or past the radius, most in the middle of the ring


def test_lenia_matches_reference():
    rule = parse("Lenia R=13 T=10 m=0.15 s=0.015 b=1")
    field = Field(128, rule)
    field.seed(0.5, spot=True, seed=4)
    cells = field.cells.astype(np.float64)
    for _ in range(20):
        field.step()
        cells = lenia_reference(cells, rule)
    assert np.abs(field.cells - cells).max() < 1e-3


@pytest.mark.parametrize("code", ["O2u", "S1s", "K4s", "3GH2s"])
def test_lenia_creatures_live(code):
    creature = species(code)
    field = Field(256, creature.rule)
    field.stamp(creature.cells, 100, 100)
    mass = field.population
    field.step(300)
    assert abs(field.population - mass) < 0.1 * mass


def test_orbium_swims():
    orbium = species("O2u")
    field = Field(128, orbium.rule)
    field.stamp(orbium.cells, 54, 54)
    start = field.cells.copy()
    field.step(100)
    assert np.abs(field.cells - start).sum() > 0.5 * start.sum()   # it has moved off its start


def test_lenia_seeding_scatters_the_creature():
    orbium = species("O2u")
    field = Field(256, orbium.rule)
    field.seed(0.3, spot=False, seed=2, species=orbium.cells)
    assert field.population > 2 * orbium.cells.sum()


# --- RLE and stamping ----------------------------------------------------------------------------

GLIDER_RLE = "#N Glider\n#C A comment.\nx = 3, y = 3, rule = B3/S23\nbob$2bo$3o!\n"


def test_rle_reads_a_glider():
    p = parse_rle(GLIDER_RLE)
    assert p.name == "Glider" and p.comments == ("A comment.",)
    assert p.cells.tolist() == [[0, 1, 0], [0, 0, 1], [1, 1, 1]]


def test_rle_without_header_or_rule():
    assert parse_rle("bo$2bo$3o!").cells.sum() == 5
    p = parse_rle("x = 3, y = 2\n3o$o!")
    assert str(p.rule) == "B3/S23" and p.cells.shape == (2, 3)


def test_rle_golly_bounded_grid_suffix_is_ignored():
    assert str(parse_rle("x = 1, y = 1, rule = B36/S23:T100,100\no!").rule) == "B36/S23"


@pytest.mark.parametrize("text", ["", "hello", "x = 2, y = 2, rule = B3/S23\n2b$2b!",
                                  "x = 1, y = 1, rule = LifeHistory\nA!", "x = 2, y = 1, rule = B3/S23\nAB!"])
def test_rle_errors(text):
    with pytest.raises(PatternError):
        parse_rle(text)


@pytest.mark.parametrize("group", ["Life", "HighLife", "Wireworld", "Lenia"])
def test_library_round_trips_through_rle(group):
    for pattern in library()[group]:
        again = parse_rle(to_rle(pattern))
        assert again.rule == pattern.rule and again.name == pattern.name
        if group == "Lenia":
            assert np.abs(again.cells - pattern.cells).max() <= 0.5 / 255 + 1e-6
        else:
            assert np.array_equal(again.cells, pattern.cells)


def test_multistate_letters_round_trip():
    cells = np.array([[0, 1, 24, 25, 48, 49, 255]], dtype=np.int64)
    p = Pattern("x", parse("Lenia R=13 T=10 m=0.15 s=0.015 b=1"), (cells / 255).astype(np.float32))
    assert np.array_equal(np.rint(parse_rle(to_rle(p)).cells * 255), cells)


def test_stamp_wraps_around_and_extract_finds_it():
    field = Field(16)
    glider = parse_rle(GLIDER_RLE)
    field.stamp(glider.cells, 15, 15)   # top-left corner on the last cell: the rest wraps to the start
    assert field.population == 5
    assert field.state[15, 0] == 1 and field.state[1, 0] == 1
    field.clear()
    field.stamp(glider.cells, 5, 6)
    assert np.array_equal(field.extract(), glider.cells)
    assert field.age[7, 6] == 1


def test_rotated_pattern_turns_clockwise():
    p = parse_rle("x = 2, y = 1\n2o!")
    assert p.rotated().cells.shape == (2, 1)
    assert p.rotated(4).cells.tolist() == p.cells.tolist()


# --- the Life library behaves -------------------------------------------------------------------

def shape_of(state):
    ys, xs = np.nonzero(state == 1)
    return tuple(ys - ys.min()), tuple(xs - xs.min())


@pytest.mark.parametrize("name,period", [("Glider", 4), ("Lightweight spaceship", 4), ("Copperhead", 10),
                                         ("Pulsar", 3), ("Pentadecathlon", 15), ("Queen bee shuttle", 30)])
def test_life_library_periods(name, period):
    pattern = next(p for p in library()["Life"] if p.name == name)
    field = Field(128, pattern.rule)
    field.stamp(pattern.cells, 50, 50)
    start = shape_of(field.state)
    field.step(period)
    assert shape_of(field.state) == start


def test_r_pentomino_settles_at_116():
    pattern = next(p for p in library()["Life"] if p.name == "R-pentomino")
    field = Field(1024, pattern.rule)
    field.stamp(pattern.cells, 510, 510)
    field.step(1103)
    assert field.population == 116


def test_gosper_gun_adds_a_glider_every_30():
    pattern = next(p for p in library()["Life"] if p.name == "Gosper glider gun")
    field = Field(256, pattern.rule)
    field.stamp(pattern.cells, 100, 100)
    field.step(30)
    before = field.population
    field.step(30)
    assert field.population == before + 5


def test_highlife_replicator_copies_itself():
    pattern = library()["HighLife"][0]
    field = Field(128, pattern.rule)
    field.stamp(pattern.cells, 60, 60)
    field.step(12)
    assert field.population == 2 * int(pattern.cells.sum())
