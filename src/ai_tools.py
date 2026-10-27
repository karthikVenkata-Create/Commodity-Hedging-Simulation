"""
The tools Claude can call. Each one is a thin wrapper around code that already
exists in this repo (hedge_engine.py, stress_test.py, pricing.py), so every number
the AI reports comes from the same functions the tests and the Excel report use.
Claude decides which tool to call and with what inputs; the math happens here.

All money is in whole dollars and all probabilities are in percent, so the
guardrail in ai_analyst.py can match the figures in an answer back to a tool result.
"""

import numpy as np
import pandas as pd

from hedge_engine import UNITS, hedged_revenue, headline, load_rounds, settle
from memo_search import search_memos
from pricing import collar, zero_cost_call
from stress_test import PERIOD_YEARS, RISK_FREE, realized_vol, risk_metrics, simulate_spots


class ToolError(ValueError):
    """Bad input from the model. The message goes back to Claude so it can fix the call."""


def _book():
    return settle(load_rounds())


def _row(round):
    s = _book()
    if round not in set(s["round"]):
        raise ToolError(f"round must be one of {sorted(s['round'].astype(int))}, got {round}")
    return s.loc[s["round"] == round].iloc[0].copy()


def _num(x, digits=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return int(round(float(x))) if digits == 0 else round(float(x), digits)


def _sigma(sigma):
    if sigma is None:
        return realized_vol(_book()["spot"])
    if not 0.05 <= sigma <= 2.0:
        raise ToolError("sigma is per-round volatility as a decimal, between 0.05 and 2.0 (e.g. 0.74)")
    return sigma


def _position(r):
    p = {"swap_qty": _num(r["swap_qty"]), "swap_price": _num(r["swap_price"], 2),
         "collar_qty": _num(r["collar_qty"]), "float_qty": _num(r["float_qty"])}
    if r["collar_qty"] > 0:
        p.update(put_strike=_num(r["put_strike"], 2), call_strike=_num(r["call_strike"], 2))
    p["hedge_ratio_pct"] = _num((r["swap_qty"] + r["collar_qty"]) / UNITS * 100, 1)
    return p


def _metrics(rev, r):
    m = risk_metrics(rev, r["bankruptcy_line"], r["investment_hurdle"])
    return {
        "expected_revenue": _num(m["mean_M"] * 1e6),
        "p05_revenue": _num(m["p05_M"] * 1e6),
        "var95": _num(m["var95_M"] * 1e6),
        "expected_shortfall95": _num(m["es95_M"] * 1e6),
        "worst_case_revenue": _num(m["worst_M"] * 1e6),
        "p_bankrupt_pct": _num(m["p_bankrupt"] * 100, 1) if pd.notna(m["p_bankrupt"]) else None,
        "p_hurdle_pct": _num(m["p_hurdle"] * 100, 1) if pd.notna(m["p_hurdle"]) else None,
    }


def _alt_row(r, swap_qty, collar_qty, put_strike, call_strike):
    """Same round, same market prices, different book. Unspecified fields keep my actual position."""
    a = r.copy()
    a["swap_qty"] = r["swap_qty"] if swap_qty is None else swap_qty
    a["collar_qty"] = r["collar_qty"] if collar_qty is None else collar_qty
    if a["collar_qty"] > 0:
        a["put_strike"] = put_strike if put_strike is not None else r["put_strike"]
        a["call_strike"] = call_strike if call_strike is not None else r["call_strike"]
        if pd.isna(a["put_strike"]) or pd.isna(a["call_strike"]):
            raise ToolError("a collar needs both put_strike and call_strike (this round had no collar to copy)")
        if not 0 < a["put_strike"] < a["call_strike"]:
            raise ToolError("need 0 < put_strike < call_strike")
    if a["swap_qty"] < 0 or a["collar_qty"] < 0:
        raise ToolError("quantities can't be negative")
    if a["swap_qty"] + a["collar_qty"] > UNITS:
        raise ToolError(f"swap_qty + collar_qty can't exceed {UNITS:,} units")
    a["float_qty"] = UNITS - a["swap_qty"] - a["collar_qty"]
    return a


# ---------------------------------------------------------------- tools

def get_round(round):
    """What I actually held in a round and how it settled."""
    r = _row(round)
    return {
        "round": int(r["round"]),
        "position": _position(r),
        "settled_spot": _num(r["spot"], 2),
        "swap_pnl": _num(r["swap_pnl"]),
        "collar_pnl": _num(r["collar_pnl"]),
        "hedged_revenue": _num(r["hedged_rev"]),
        "unhedged_revenue": _num(r["unhedged_rev"]),
        "hedging_gain_vs_unhedged": _num(r["hedged_rev"] - r["unhedged_rev"]),
        "bankruptcy_line": _num(r["bankruptcy_line"]),
        "investment_hurdle": _num(r["investment_hurdle"]),
        "spot_price_needed_unhedged_to_stay_above_bankruptcy_line": _num(r["bankruptcy_line"] / UNITS, 2),
        "spot_price_needed_unhedged_to_clear_hurdle": _num(r["investment_hurdle"] / UNITS, 2),
        "cleared_hurdle": None if pd.isna(r["investment_hurdle"]) else bool(r["hedged_rev"] >= r["investment_hurdle"]),
        "memo_reported_revenue": _num(r["memo_reported_revenue"]),
        "matches_memo": bool(r["matches_memo"]),
    }


def portfolio_summary():
    """Whole-game totals: revenue hedged vs unhedged, cost of hedging, volatility."""
    s = _book()
    h = headline(s)
    return {
        "rounds_settled": h["rounds_settled"],
        "total_hedged_revenue": _num(h["total_hedged_M"] * 1e6),
        "total_unhedged_revenue": _num(h["total_unhedged_M"] * 1e6),
        "cost_of_hedging": _num(h["cost_of_hedging_M"] * 1e6),
        "cost_of_hedging_pct_of_unhedged": _num(h["cost_pct_of_unhedged"], 1),
        "revenue_volatility_reduction_pct": _num(h["vol_reduction_pct"], 1),
        "lowest_round_hedged": _num(h["min_hedged_M"] * 1e6),
        "lowest_round_unhedged": _num(h["min_unhedged_M"] * 1e6),
        "per_round_volatility_pct": _num(realized_vol(s["spot"]) * 100, 1),
        "rounds_with_stated_bankruptcy_and_hurdle": h["rounds_with_stated_lines"],
        "hedged_rounds_clearing_hurdle": h["hedged_rounds_clearing_hurdle"],
        "unhedged_rounds_clearing_hurdle": h["unhedged_rounds_clearing_hurdle"],
    }


def evaluate_hedge(round, swap_qty=None, collar_qty=None, put_strike=None, call_strike=None, sigma=None):
    """Settle and stress-test a book for one round. With no changes it tests my actual book;
    pass any of the quantities or strikes to test an alternative. The swap price is the
    round's market price and can't be changed. Returns the alternative next to my actual
    book and the fully unhedged book, plus the differences, so no arithmetic is left to do."""
    r = _row(round)
    a = _alt_row(r, swap_qty, collar_qty, put_strike, call_strike)
    sig = _sigma(sigma)
    spots = simulate_spots(r["swap_price"], sig)
    tested = _metrics(hedged_revenue(a, spots), r)
    actual = _metrics(hedged_revenue(r, spots), r)
    unhedged = _metrics(UNITS * spots, r)
    settled = float(hedged_revenue(a, r["spot"]))

    def diff(x, y):
        return {k: (None if x[k] is None or y[k] is None else _num(x[k] - y[k], 1 if k.endswith("pct") else 0))
                for k in x}

    return {
        "round": int(r["round"]),
        "tested_position": _position(a),
        "is_my_actual_position": bool(all(np.isclose(np.nan_to_num(a[k]), np.nan_to_num(r[k]))
                                          for k in ["swap_qty", "collar_qty", "put_strike", "call_strike"])),
        "settled_spot": _num(r["spot"], 2),
        "settled_revenue": _num(settled),
        "settled_revenue_vs_my_actual": _num(settled - r["hedged_rev"]),
        "settled_revenue_vs_unhedged": _num(settled - r["unhedged_rev"]),
        "bankruptcy_line": _num(r["bankruptcy_line"]),
        "investment_hurdle": _num(r["investment_hurdle"]),
        "spot_price_needed_unhedged_to_clear_hurdle": _num(r["investment_hurdle"] / UNITS, 2),
        "stress_test": {
            "scenarios": len(spots),
            "per_round_volatility_pct": _num(sig * 100, 1),
            "forward_price": _num(r["swap_price"], 2),
            "tested_position": tested,
            "my_actual_position": actual,
            "unhedged": unhedged,
            "tested_minus_my_actual": diff(tested, actual),
            "tested_minus_unhedged": diff(tested, unhedged),
            "var95_cut_vs_unhedged_pct": _num((1 - tested["var95"] / unhedged["var95"]) * 100, 1),
            "var95_cut_vs_my_actual_pct": _num((1 - tested["var95"] / actual["var95"]) * 100, 1) if actual["var95"] else None,
        },
    }


def price_collar(round, put_strike, call_strike, sigma=None):
    """Black-76 fair value of a collar (long put, short call) at that round's forward,
    and the call strike that would have made it truly zero-cost."""
    r = _row(round)
    if not 0 < put_strike < call_strike:
        raise ToolError("need 0 < put_strike < call_strike")
    sig = _sigma(sigma)
    sig_annual = sig / np.sqrt(PERIOD_YEARS)   # same convention as stress_test.collar_pricing
    F = r["swap_price"]
    c = collar(F, put_strike, call_strike, sig_annual, RISK_FREE, PERIOD_YEARS)
    kc = zero_cost_call(F, put_strike, sig_annual, RISK_FREE, PERIOD_YEARS)
    return {
        "round": int(r["round"]),
        "forward_price": _num(F, 2),
        "put_strike": put_strike,
        "call_strike": call_strike,
        "put_premium_per_unit": _num(c["put_premium"], 2),
        "call_premium_per_unit": _num(c["call_premium"], 2),
        "net_cost_per_unit": _num(c["net_premium"], 2),
        "note": "net_cost_per_unit > 0 means the put is worth more than the call, so a 'free' collar at these strikes is a gift to the hedger",
        "zero_cost_call_strike": _num(kc, 2),
        "per_round_volatility_pct": _num(sig * 100, 1),
    }


def memo_search(query, round=None, top_k=3):
    """Search my original decision memos."""
    if not 1 <= top_k <= 8:
        raise ToolError("top_k must be between 1 and 8")
    hits = search_memos(query, round=round, top_k=top_k)
    return {"results": [{k: h[k] for k in ("memo", "section", "round", "text", "score")} for h in hits]}


# ---------------------------------------------------------------- schemas sent to Claude

ROUND = {"type": "integer", "minimum": 1, "maximum": 7, "description": "Round number, 1 to 7"}
SIGMA = {"type": "number", "description": "Optional per-round volatility as a decimal (e.g. 0.5). Defaults to the game's realized volatility, about 0.74."}

TOOLS = [
    {
        "name": "get_round",
        "description": "Get what I actually held in a round (swap, collar, floating units) and how it settled: spot price, swap and collar P&L, hedged vs unhedged revenue, the bankruptcy line and investment hurdle, and whether my memo's number matches the recomputed one.",
        "input_schema": {"type": "object", "properties": {"round": ROUND}, "required": ["round"]},
    },
    {
        "name": "portfolio_summary",
        "description": "Whole-game totals across the seven settled rounds: total hedged and unhedged revenue, the cost of hedging, how much hedging cut round-to-round volatility, and the game's realized volatility.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "evaluate_hedge",
        "description": "Settle and Monte Carlo stress-test (10,000 scenarios) a hedge book for one round. Call with only `round` to test my actual book. Pass swap_qty, collar_qty, put_strike or call_strike to test an alternative; anything left out keeps my actual value, and floating units are whatever is left of 100,000. Returns expected revenue, 5th percentile, VaR, expected shortfall, probability of falling below the bankruptcy line and of clearing the investment hurdle, for the tested book, my actual book and a fully unhedged book, plus the differences. Use this for any what-if question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "round": ROUND,
                "swap_qty": {"type": "integer", "minimum": 0, "maximum": 100000, "description": "Units sold forward at the round's swap price"},
                "collar_qty": {"type": "integer", "minimum": 0, "maximum": 100000, "description": "Units covered by a collar (long put, short call)"},
                "put_strike": {"type": "number", "description": "Collar put strike"},
                "call_strike": {"type": "number", "description": "Collar call strike"},
                "sigma": SIGMA,
            },
            "required": ["round"],
        },
    },
    {
        "name": "price_collar",
        "description": "Black-76 fair value of a collar at a round's forward price: put and call premiums per unit, net cost, and the call strike that would make the collar exactly zero-cost. Use it to judge whether the game's 'free' collars were fair.",
        "input_schema": {
            "type": "object",
            "properties": {"round": ROUND, "put_strike": {"type": "number"}, "call_strike": {"type": "number"}, "sigma": SIGMA},
            "required": ["round", "put_strike", "call_strike"],
        },
    },
    {
        "name": "memo_search",
        "description": "Search the decision memos I wrote during the game (Oct to Dec 2025) for my reasoning at the time. Returns the best-matching memo sections. Use `round` to limit results to one round's result or decision.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to search for, e.g. 'why collar call 75'"},
                "round": ROUND,
                "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query"],
        },
    },
]

FUNCTIONS = {
    "get_round": get_round,
    "portfolio_summary": portfolio_summary,
    "evaluate_hedge": evaluate_hedge,
    "price_collar": price_collar,
    "memo_search": memo_search,
}


def run_tool(name, args):
    """Run a tool by name. Returns (result, is_error). Errors go back to Claude as text."""
    if name not in FUNCTIONS:
        return f"unknown tool {name}", True
    try:
        return FUNCTIONS[name](**args), False
    except ToolError as e:
        return str(e), True
    except TypeError as e:
        return f"bad arguments for {name}: {e}", True
