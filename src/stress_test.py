"""
Monte Carlo stress test of every round's hedge book.

For each settled round, the position I actually held is run through 10,000
simulated settlement prices. The question is the one a treasury desk asks before
the trade, not after it: given the book, how bad can revenue get, how likely is
the bankruptcy line, and how likely is funding the investment?

Scenario model
- Settlement spot is lognormal, centered on the forward (taken as the round's swap price,
  the market's fixed price when I traded).
- Volatility is estimated from the game itself: the standard deviation of round-to-round
  log changes in the settled spot. One round = one period (T = 1).
- A fixed seed makes every run reproducible.
"""

import numpy as np
import pandas as pd

from hedge_engine import UNITS, hedged_revenue, load_rounds, settle
from pricing import black76, collar, zero_cost_call

N_SCENARIOS = 10_000
SEED = 2025
RISK_FREE = 0.04            # annual, used only for option discounting
PERIOD_YEARS = 1 / 12       # discounting horizon per round (premiums are tiny-rate sensitive)


def realized_vol(spots):
    """Per-round volatility from the game's settled prices."""
    logret = np.diff(np.log(np.asarray(spots, dtype=float)))
    return float(np.std(logret, ddof=1))


def simulate_spots(F, sigma, n=N_SCENARIOS, seed=SEED):
    z = np.random.default_rng(seed).standard_normal(n)
    return F * np.exp(-0.5 * sigma**2 + sigma * z)


def risk_metrics(rev, bankruptcy=None, hurdle=None):
    q05 = np.quantile(rev, 0.05)
    out = {
        "mean_M": rev.mean() / 1e6,
        "std_M": rev.std() / 1e6,
        "p05_M": q05 / 1e6,
        "var95_M": (rev.mean() - q05) / 1e6,
        "es95_M": (rev.mean() - rev[rev <= q05].mean()) / 1e6,
        "worst_M": rev.min() / 1e6,
    }
    out["p_bankrupt"] = float((rev < bankruptcy).mean()) if pd.notna(bankruptcy) else np.nan
    out["p_hurdle"] = float((rev >= hurdle).mean()) if pd.notna(hurdle) else np.nan
    return out


def stress_round(row, sigma, n=N_SCENARIOS, seed=SEED):
    spots = simulate_spots(row["swap_price"], sigma, n, seed)
    h = risk_metrics(hedged_revenue(row, spots), row["bankruptcy_line"], row["investment_hurdle"])
    u = risk_metrics(UNITS * spots, row["bankruptcy_line"], row["investment_hurdle"])
    rec = {"round": int(row["round"]), "forward": row["swap_price"], "sigma": sigma}
    rec.update({f"hedged_{k}": v for k, v in h.items()})
    rec.update({f"unhedged_{k}": v for k, v in u.items()})
    rec["var_reduction_pct"] = (1 - h["var95_M"] / u["var95_M"]) * 100
    return rec


def stress_table(s, sigma):
    return pd.DataFrame([stress_round(r, sigma) for _, r in s.iterrows()])


def collar_pricing(s, sigma, r=RISK_FREE, T=PERIOD_YEARS):
    """Fair value of each collar I traded, and the strike that would have made it zero-cost.
    The game treated every collar as free; this shows what each one was worth at market prices."""
    rows = []
    for _, x in s[s["collar_qty"] > 0].iterrows():
        F = x["swap_price"]
        # put the pricing horizon on the same footing as the simulation: one round of vol
        sig_annual = sigma / np.sqrt(T)
        c = collar(F, x["put_strike"], x["call_strike"], sig_annual, r, T)
        kc = zero_cost_call(F, x["put_strike"], sig_annual, r, T)
        rows.append({
            "round": int(x["round"]), "forward": F, "put_strike": x["put_strike"],
            "game_call_strike": x["call_strike"], "zero_cost_call_strike": kc,
            "put_premium": c["put_premium"], "call_premium": c["call_premium"],
            "net_premium_per_unit": c["net_premium"],
            "game_edge_vs_market_M": c["net_premium"] * x["collar_qty"] / 1e6,
            "collar_delta": c["delta"], "collar_gamma": c["gamma"],
            "book_delta_units": x["float_qty"] + x["collar_qty"] * (1 + c["delta"] / np.exp(-r * T)),
        })
    return pd.DataFrame(rows)


def vol_sensitivity(s, sigmas=(0.20, 0.35, 0.50, 0.65, 0.80, 0.95)):
    """VaR reduction and hurdle probability for each round across a range of vols."""
    rows = []
    for sig in sigmas:
        for _, r in s.iterrows():
            m = stress_round(r, sig)
            rows.append({"sigma": sig, "round": m["round"], "var_reduction_pct": m["var_reduction_pct"],
                         "hedged_p_hurdle": m["hedged_p_hurdle"], "unhedged_p_hurdle": m["unhedged_p_hurdle"],
                         "hedged_p_bankrupt": m["hedged_p_bankrupt"], "unhedged_p_bankrupt": m["unhedged_p_bankrupt"]})
    return pd.DataFrame(rows)


def run(sigma=None):
    s = settle(load_rounds())
    sig = realized_vol(s["spot"]) if sigma is None else sigma
    return s, sig, stress_table(s, sig), collar_pricing(s, sig), vol_sensitivity(s)


if __name__ == "__main__":
    s, sig, st, cp, vs = run()
    pd.set_option("display.width", 200)
    print(f"Realized per-round volatility from game prices: {sig:.1%}\n")
    print(st[["round", "forward", "hedged_var95_M", "unhedged_var95_M", "var_reduction_pct",
              "hedged_p_bankrupt", "unhedged_p_bankrupt", "hedged_p_hurdle", "unhedged_p_hurdle"]].round(3).to_string(index=False))
    print("\n", cp.round(3).to_string(index=False))
