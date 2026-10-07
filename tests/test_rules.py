import pytest

from cellbox.rules import PRESETS, Rule, RuleError, parse, preset_name


@pytest.mark.parametrize("text", ["B3/S23", "b3/s23", "B3S23", " B3 / S23 ", "23/3"])
def test_conway_spellings(text):
    assert parse(text) == Rule(frozenset({3}), frozenset({2, 3}))


@pytest.mark.parametrize("text", ["B2/S/C3", "B2/S/G3", "B2SC3", "/2/3"])
def test_brians_brain_spellings(text):
    assert parse(text) == Rule(frozenset({2}), frozenset(), 3)


def test_generations_sbc_form():
    assert parse("345/2/4") == parse("B2/S345/C4")


def test_two_states_is_life_like():
    rule = parse("B3/S23/C2")
    assert not rule.is_generations
    assert str(rule) == "B3/S23"


def test_canonical_text_sorts_and_dedupes():
    assert str(parse("B633/S32")) == "B36/S23"
    assert str(parse("b2/s/c3")) == "B2/S/C3"


@pytest.mark.parametrize("text", ["", "B9/S23", "B3/S2a", "hello", "B3/S23/C1", "B3/S23/C999", "3/23/x"])
def test_invalid(text):
    with pytest.raises(RuleError):
        parse(text)


def test_presets_round_trip():
    for preset in PRESETS:
        assert parse(str(preset.rule)) == preset.rule
        assert preset_name(preset.rule) == preset.name


def test_custom_rule_has_no_name():
    assert preset_name(parse("B1/S1")) is None
