import pandas as pd

from index.index_engine import compute_weighted_index


def test_index_equals_100_when_no_price_change():
    merged = pd.DataFrame(
        {
            "weight": [0.6, 0.4],
            "price_today": [4000, 3000],
            "price_base": [4000, 3000],
        }
    )
    assert compute_weighted_index(merged) == 100.0


def test_index_reflects_uniform_price_increase():
    # Every route's price is +10% vs base -> index should be 110, regardless of weights.
    merged = pd.DataFrame(
        {
            "weight": [0.7, 0.3],
            "price_today": [4400, 3300],
            "price_base": [4000, 3000],
        }
    )
    assert round(compute_weighted_index(merged), 2) == 110.0


def test_heavier_route_dominates_the_index():
    # DEL-BOM (weight 0.9) up 50%, a minor route (weight 0.1) down 50%.
    merged = pd.DataFrame(
        {
            "weight": [0.9, 0.1],
            "price_today": [6000, 1500],
            "price_base": [4000, 3000],
        }
    )
    # Expected: 0.9*1.5*100 + 0.1*0.5*100 = 135 + 5 = 140
    assert round(compute_weighted_index(merged), 2) == 140.0


def test_weights_renormalize_when_a_route_is_missing():
    # Only one route has data today; its weight should be treated as 1.0
    # after re-normalization, not diluted by the missing route's original weight.
    merged = pd.DataFrame(
        {
            "weight": [0.4],  # originally part of a larger basket
            "price_today": [4400],
            "price_base": [4000],
        }
    )
    assert round(compute_weighted_index(merged), 2) == 110.0
