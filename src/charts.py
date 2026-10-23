"""Charts for the README. Run after hedge_engine.py (it reads outputs/)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hedge_engine import load_rounds, settle, hedged_revenue, UNITS

OUT = Path(__file__).resolve().parents[1] / "outputs"
HEDGED, UNHEDGED = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})


def revenue_by_round(s):
    fig, ax = plt.subplots(figsize=(10, 5.4))
    x = np.arange(len(s))
    w = 0.38
    ax.bar(x - w / 2 - 0.01, s["hedged_rev"] / 1e6, w, color=HEDGED, label="My hedged book")
    ax.bar(x + w / 2 + 0.01, s["unhedged_rev"] / 1e6, w, color=UNHEDGED, label="If fully unhedged")
    for i, r in s.reset_index().iterrows():
        if pd.notna(r["bankruptcy_line"]):
            ax.hlines(r["bankruptcy_line"] / 1e6, i - 0.45, i + 0.45, colors=INK, linestyles=":", lw=1.5)
            ax.hlines(r["investment_hurdle"] / 1e6, i - 0.45, i + 0.45, colors=INK, linestyles="--", lw=1.2)
        ax.text(i - w / 2, r["hedged_rev"] / 1e6 + 0.3, f"{r['hedged_rev']/1e6:.1f}", ha="center", fontsize=8.5, color=INK)
        ax.text(i + w / 2, r["unhedged_rev"] / 1e6 + 0.3, f"{r['unhedged_rev']/1e6:.1f}", ha="center", fontsize=8.5, color=INK2)
    ax.plot([], [], color=INK, ls=":", label="Bankruptcy line (where stated)")
    ax.plot([], [], color=INK, ls="--", label="Investment hurdle (where stated)")
    ax.set_xticks(x, [f"R{int(r)}\nspot ${sp:g}" for r, sp in zip(s["round"], s["spot"])])
    ax.set_ylabel("Revenue ($M)")
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Hedged vs unhedged revenue, settled rounds 1-7", loc="left", fontsize=13, color=INK, fontweight="bold")
    ax.legend(frameon=False, ncol=2, loc="upper left", fontsize=9)
    ax.set_ylim(0, 25)
    fig.tight_layout()
    fig.savefig(OUT / "revenue_by_round.png", dpi=200)
    plt.close(fig)


def payoff_profiles(s):
    """R5 vs R7: same game, two very different payoff shapes."""
    spots = np.linspace(0, 320, 641)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, rnd, note in [(axes[0], 5, "R5: collar call at \\$75 caps 60k units,\nhurdle needs spot ~\\$332 (unreachable)"),
                          (axes[1], 7, "R7: \\$200 put + \\$210 swap floor the book,\n\\$16.3M even if spot went to zero")]:
        r = s.loc[s["round"] == rnd].iloc[0]
        ax.plot(spots, UNITS * spots / 1e6, color=UNHEDGED, lw=2, label="Unhedged")
        ax.plot(spots, hedged_revenue(r, spots) / 1e6, color=HEDGED, lw=2, label="My hedged book")
        ax.axhline(r["bankruptcy_line"] / 1e6, color=INK, ls=":", lw=1.3, label="Bankruptcy line")
        ax.axhline(r["investment_hurdle"] / 1e6, color=INK, ls="--", lw=1.1, label="Investment hurdle")
        ax.axvline(r["spot"], color=INK2, lw=0.8)
        ax.scatter([r["spot"]], [r["hedged_rev"] / 1e6], s=40, color=HEDGED, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.annotate(f"settled ${r['spot']:g}", (r["spot"], 0.6), xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=INK2)
        ax.set_title(note, loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Spot price at settlement ($/unit)")
        ax.yaxis.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(0, 320)
        ax.set_ylim(0, 32)
    axes[0].set_ylabel("Revenue ($M)")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle("Payoff profile: how each round's book responds to spot", x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "payoff_profiles_R5_R7.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    s = settle(load_rounds())
    revenue_by_round(s)
    payoff_profiles(s)
    print("charts saved to outputs/")
