"""
Black-76 option pricing for commodity forwards.

Commodity options settle against a forward or futures price, so Black-76 is the
standard model (Black-Scholes with the forward replacing spot and no carry term).
Used here to put a fair market price on each collar in the game and to solve the
call strike that would have made each collar truly zero-cost.
"""

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def _d1_d2(F, K, sigma, T):
    sT = sigma * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / sT
    return d1, d1 - sT


def black76(F, K, sigma, r, T, kind):
    """Price, delta and gamma of a European call or put on a forward.
    Delta is the sensitivity of the option's value to the forward price,
    gamma is the sensitivity of that delta. Both are per unit of commodity."""
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    df = np.exp(-r * T)
    d1, d2 = _d1_d2(F, K, sigma, T)
    if kind == "call":
        price = df * (F * norm.cdf(d1) - K * norm.cdf(d2))
        delta = df * norm.cdf(d1)
    else:
        price = df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
        delta = -df * norm.cdf(-d1)
    gamma = df * norm.pdf(d1) / (F * sigma * np.sqrt(T))
    return {"price": float(price), "delta": float(delta), "gamma": float(gamma)}


def collar(F, put_strike, call_strike, sigma, r, T):
    """Long put / short call, per unit. Net premium > 0 means the collar costs money."""
    p = black76(F, put_strike, sigma, r, T, "put")
    c = black76(F, call_strike, sigma, r, T, "call")
    return {
        "put_premium": p["price"], "call_premium": c["price"],
        "net_premium": p["price"] - c["price"],
        "delta": p["delta"] - c["delta"], "gamma": p["gamma"] - c["gamma"],
    }


def zero_cost_call(F, put_strike, sigma, r, T):
    """Call strike whose premium exactly funds the put. Call value falls as the
    strike rises, so there is one root; brentq finds it."""
    target = black76(F, put_strike, sigma, r, T, "put")["price"]
    f = lambda k: black76(F, k, sigma, r, T, "call")["price"] - target
    return brentq(f, 1e-6 * F, 50 * F, xtol=1e-8)
