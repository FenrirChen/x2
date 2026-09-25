"""Pure analysis formulas checked against ARM64 branch reconstruction."""

from fractions import Fraction

import pytest

from tools.analysis.calculate_drop_probability import (
    UnresolvedDropAlgorithm, calculate, marginal, source_tables,
)


@pytest.fixture(scope="module")
def tables():
    return source_tables()


def test_single_pick_uses_nodrop_plus_prob_weight(tables):
    groups, items, _ = tables
    # Picks=1, NoDrop=70, Prob=[30].
    assert marginal(1309118, 1109011, groups, items) == (Fraction(3, 10), Fraction(7, 10))


def test_sum_over_100_is_still_weighted_not_independent(tables):
    groups, items, names = tables
    result = calculate(1309102, groups, items, names)
    assert [(row["item_id"], row["p_at_least_one"]) for row in result["items"]] == [
        (1101031, "5/16"), (1101032, "49/160"), (1101033, "1/160")]


def test_repeated_picks_are_with_replacement(tables):
    groups, items, _ = tables
    # Picks=5, NoDrop=30, Prob=[70] -> five independent weighted selections.
    expected, zero = marginal(1309116, 1101021, groups, items)
    assert expected == Fraction(7, 2)
    assert zero == Fraction(3, 10) ** 5


def test_negative_picks_use_prob_as_deterministic_count(tables):
    groups, items, _ = tables
    assert marginal(1309010, 1101021, groups, items) == (Fraction(5), Fraction(0))
    assert marginal(1309010, 1100001, groups, items) == (Fraction(1), Fraction(0))


def test_raw_prob_one_can_mean_certain_item(tables):
    groups, items, _ = tables
    assert marginal(1309250, 1104048, groups, items) == (Fraction(1), Fraction(0))


def test_adc_nested_group_is_not_falsely_calculated(tables):
    groups, items, names = tables
    with pytest.raises(UnresolvedDropAlgorithm, match="IsADC"):
        calculate(1309024, groups, items, names)
