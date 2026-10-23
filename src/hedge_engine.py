"""
Commodity Hedging Simulation - settlement and risk engine
Karthik Bommisetty | UIC MBA Finance + MS Business Analytics

Recomputes every settled round of the Fall 2025 hedging game from my original
decision memos (data/rounds.csv), checks each result against the number I
wrote in the memo at the time, then runs the risk analysis on top of it.

Settlement rule used in the game (per round, 100,000 units):
    revenue = 100,000 * spot
            + swap_qty   * (swap_price - spot)
            + collar_qty * [max(put - spot, 0) - max(spot - call, 0)]
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rounds.csv"
OUT = ROOT / "outputs"
UNITS = 100_000


def load_rounds(path=DATA):
    df = pd.read_csv(path)
    df[["collar_qty", "swap_qty", "float_qty"]] = df[["collar_qty", "swap_qty", "float_qty"]].fillna(0)
    total = df["swap_qty"] + df["collar_qty"] + df["float_qty"]
    if not (total == UNITS).all():
        raise ValueError("every round must allocate exactly 100,000 units")
    return df


def hedged_revenue(row, spot):
    """Revenue for one round's position at any spot price (spot can be an array)."""
    spot = np.asarray(spot, dtype=float)
    rev = UNITS * spot + row["swap_qty"] * (row["swap_price"] - spot)
    if row["collar_qty"] > 0:
        put = np.maximum(row["put_strike"] - spot, 0)
        call = np.maximum(spot - row["call_strike"], 0)
        rev = rev + row["collar_qty"] * (put - call)
    return rev


def settle(df):
    """Settle every round at the realized spot and split out the hedge P&L."""
    out = df.copy()
    out["unhedged_rev"] = UNITS * out["spot"]
    out["swap_pnl"] = out["swap_qty"] * (out["swap_price"] - out["spot"])
    put = np.maximum(out["put_strike"] - out["spot"], 0).fillna(0)
    call = np.maximum(out["spot"] - out["call_strike"], 0).fillna(0)
    out["collar_pnl"] = out["collar_qty"] * (put - call)
    out["hedge_pnl"] = out["swap_pnl"] + out["collar_pnl"]
    out["hedged_rev"] = out["unhedged_rev"] + out["hedge_pnl"]
    out["matches_memo"] = np.isclose(out["hedged_rev"], out["memo_reported_revenue"], atol=1)
    out["hedge_ratio"] = (out["swap_qty"] + out["collar_qty"]) / UNITS
    return out


def headline(s):
    """Portfolio-level numbers used in the README."""
    h, u = s["hedged_rev"], s["unhedged_rev"]
    stated = s.dropna(subset=["bankruptcy_line"])
    return {
        "rounds_settled": len(s),
        "total_hedged_M": h.sum() / 1e6,
        "total_unhedged_M": u.sum() / 1e6,
        "cost_of_hedging_M": (u.sum() - h.sum()) / 1e6,
        "cost_pct_of_unhedged": (u.sum() - h.sum()) / u.sum() * 100,
        "std_hedged_M": h.std(ddof=0) / 1e6,
        "std_unhedged_M": u.std(ddof=0) / 1e6,
        "vol_reduction_pct": (1 - h.std(ddof=0) / u.std(ddof=0)) * 100,
        "min_hedged_M": h.min() / 1e6,
        "min_unhedged_M": u.min() / 1e6,
        "hedged_rounds_below_bankruptcy": int((stated["hedged_rev"] < stated["bankruptcy_line"]).sum()),
        "unhedged_rounds_below_bankruptcy": int((stated["unhedged_rev"] < stated["bankruptcy_line"]).sum()),
        "hedged_rounds_clearing_hurdle": int((stated["hedged_rev"] >= stated["investment_hurdle"]).sum()),
        "unhedged_rounds_clearing_hurdle": int((stated["unhedged_rev"] >= stated["investment_hurdle"]).sum()),
        "rounds_with_stated_lines": len(stated),
    }


def main():
    OUT.mkdir(exist_ok=True)
    s = settle(load_rounds())
    if not s["matches_memo"].all():
        bad = s.loc[~s["matches_memo"], ["round", "hedged_rev", "memo_reported_revenue"]]
        raise AssertionError(f"recomputed revenue does not match memo:\n{bad}")

    cols = ["round", "spot", "swap_qty", "swap_price", "collar_qty", "put_strike", "call_strike",
            "float_qty", "hedge_ratio", "swap_pnl", "collar_pnl", "hedge_pnl", "hedged_rev",
            "unhedged_rev", "bankruptcy_line", "investment_hurdle", "matches_memo"]
    s[cols].to_csv(OUT / "settlement.csv", index=False)

    h = headline(s)
    pd.Series(h).to_csv(OUT / "headline_metrics.csv", header=["value"])

    print("All 7 rounds recompute to the memo totals.\n")
    for k, v in h.items():
        print(f"{k:34s} {v:,.2f}" if isinstance(v, float) else f"{k:34s} {v}")
    return s, h


if __name__ == "__main__":
    main()
