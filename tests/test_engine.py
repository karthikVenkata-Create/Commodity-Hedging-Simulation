import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hedge_engine import load_rounds, settle, headline, hedged_revenue  # noqa: E402


def test_every_round_matches_memo():
    s = settle(load_rounds())
    assert s["matches_memo"].all()


def test_totals():
    h = headline(settle(load_rounds()))
    assert round(h["total_hedged_M"], 2) == 74.70
    assert round(h["total_unhedged_M"], 2) == 78.33
    assert round(h["vol_reduction_pct"]) == 30


def test_r7_floor_is_put_and_swap():
    s = settle(load_rounds())
    r7 = s.loc[s["round"] == 7].iloc[0]
    # at spot 0: 20k float earns 0, 30k swap earns 210, 50k collar earns 200
    assert np.isclose(hedged_revenue(r7, 0.0), 30_000 * 210 + 50_000 * 200)


def test_revenue_never_decreases_with_spot():
    s = settle(load_rounds())
    grid = np.linspace(0, 500, 1001)
    for _, r in s.iterrows():
        assert (np.diff(hedged_revenue(r, grid)) >= -1e-6).all()


from pricing import black76, collar, zero_cost_call  # noqa: E402
from stress_test import realized_vol, stress_round  # noqa: E402


def test_put_call_parity():
    F, K, sig, r, T = 210, 200, 0.6, 0.04, 0.25
    c = black76(F, K, sig, r, T, "call")["price"]
    p = black76(F, K, sig, r, T, "put")["price"]
    assert np.isclose(c - p, np.exp(-r * T) * (F - K), atol=1e-10)


def test_zero_cost_call_really_is_zero_cost():
    kc = zero_cost_call(210, 200, 0.6, 0.04, 0.25)
    assert abs(collar(210, 200, kc, 0.6, 0.04, 0.25)["net_premium"]) < 1e-6


def test_greeks_match_finite_differences():
    F, K, sig, r, T, h = 100, 95, 0.5, 0.04, 0.5, 1e-3
    g = black76(F, K, sig, r, T, "call")
    up = black76(F + h, K, sig, r, T, "call")["price"]
    dn = black76(F - h, K, sig, r, T, "call")["price"]
    assert np.isclose(g["delta"], (up - dn) / (2 * h), atol=1e-5)
    assert np.isclose(g["gamma"], (up - 2 * g["price"] + dn) / h**2, atol=1e-4)


def test_stress_hedge_never_increases_var():
    s = settle(load_rounds())
    sig = realized_vol(s["spot"])
    for _, r in s.iterrows():
        assert stress_round(r, sig)["var_reduction_pct"] > 0
