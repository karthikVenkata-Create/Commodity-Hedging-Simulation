# Commodity Hedging Simulation

**Karthik Bommisetty** | UIC MBA (Finance) + MS Business Analytics
[LinkedIn](https://www.linkedin.com/in/karthik-bommisetty) · [Portfolio](https://karthikvenkata-create.github.io)

In Fall 2025 I played an eight-round hedging game at UIC as the risk manager of a producer selling 100,000 units of a commodity each round. Every week I decided how much output to lock in with fixed-price swaps, how much to protect with zero-cost collars (long put, short call), and how much to leave floating. If revenue fell below the bankruptcy line the firm took a $20M penalty, and if it cleared the investment hurdle it could fund a positive-NPV project.

This repo rebuilds the game from my original weekly decision memos and stress-tests every position I took. A Python pipeline settles all seven rounds and checks each one against the number I wrote at the time. It then prices my collars with Black-76, runs each round's book through 10,000 simulated settlement prices, and exports everything to a multi-tab Excel audit report.

**[Download the audit report](outputs/hedging_audit_report.xlsx)**: Summary, Assumptions, Settlement, Collar Pricing, Stress Test, Vol Sensitivity.

## What actually happened

![Hedged vs unhedged revenue by round](outputs/revenue_by_round.png)

Over the seven settled rounds my hedged book earned $74.70M against $78.33M if I had stayed fully unhedged. Hedging cost $3.63M, about 4.6% of revenue, and cut round-to-round revenue volatility by about 30%. The best round was Round 7: spot crashed from $225 to $74, and the hedges delivered $17.78M against $7.40M unhedged. None of the rounds with a stated hurdle cleared it, hedged or unhedged.

Looking only at these results, the unhedged book never crossed a bankruptcy line either, so it is tempting to say the hedge was protecting against nothing. The stress test shows that conclusion is hindsight.

## What the stress test shows

**Volatility comes from the game itself.** Round-to-round log changes in the settled spot have a standard deviation of 74% per round. Each round's position is run through 10,000 lognormal settlement prices centered on the forward (the round's swap price) at that volatility, with a fixed seed.

**The bankruptcy risk was real.** Before each trade, staying unhedged carried a 6% to 52% chance of landing below the bankruptcy line, about 25% on average across the five rounds with a stated line. My hedges took that to about 1%. The realized prices just happened to miss the line.

**The price was the investment.** The same hedges lowered the chance of funding the project from 26% to 18% on average. In Round 5 it fell from 14% to under 1%, because a $75 collar call on 60,000 units capped revenue below the hurdle. Round 7 was the only round where hedging raised the odds (38% to 43%), because its $200 put and $210 swap sat right at the hurdle price.

**The game's collars were not all fair.** Black-76 pricing of my three collars shows the free collar in Round 5 was worth about $67K less than a fair zero-cost collar, while Rounds 6 and 7 gave me about $111K and $165K of free value. In Round 7, a truly zero-cost call against the $200 put would sit near $229 at the game's volatility, not $240.

**The result holds across volatilities.** The Vol Sensitivity tab re-runs everything from 20% to 95% volatility. Hedging cuts 95% VaR in every round at every level, and the hurdle tradeoff stays negative for Rounds 2 to 5 throughout.

![Payoff profiles for Round 5 and Round 7](outputs/payoff_profiles_R5_R7.png)

## Takeaways

At the volatility this game actually had, the hedges were doing real work: they turned a one-in-four chance of a $20M penalty into roughly one in a hundred. What I got wrong was the other side of the ledger. My strikes and sizing gave away the upside the firm needed to fund the investment, in every round but the last. Strike placement mattered more than hedge ratio. If I played again, I would set collar calls at or above the hurdle price, so the upside I give up is upside the firm doesn't need, and I would size each round from the bankruptcy and hurdle probabilities instead of defaulting to 60 to 70% hedged.

## How it works

```
data/rounds.csv          positions, strikes, settled spot and stated lines, from each memo
src/hedge_engine.py      settlement, memo check, headline metrics
src/pricing.py           Black-76 price, delta, gamma; zero-cost call solver (scipy brentq)
src/stress_test.py       10,000-scenario Monte Carlo per round, VaR / ES / probabilities, vol sensitivity
src/excel_report.py      builds outputs/hedging_audit_report.xlsx with openpyxl
src/charts.py            the two charts above
tests/test_engine.py     memo reconciliation, put-call parity, solver, Greeks vs finite differences
```

The Settlement and Collar Pricing tabs are live Excel formulas, not pasted values. Change a strike or the risk-free rate and the workbook recomputes. The zero-cost call strikes are solved in Python and then repriced in Excel, so a reviewer can see the solver's answer checked by an independent formula. Blue cells are inputs, black are formulas, and green are links between tabs.

Settlement rule for each round:

```
revenue = 100,000 x spot + swap_qty x (swap - spot)
        + collar_qty x [max(put - spot, 0) - max(spot - call, 0)]
```

## Run it

```
pip install -r requirements.txt
python src/hedge_engine.py     # settlement + checks
python src/stress_test.py      # Monte Carlo summary in the terminal
python src/excel_report.py     # writes outputs/hedging_audit_report.xlsx
python src/charts.py
pytest -q
```

## Notes on the data and model

The inputs come from my eight decision memos (Oct 13 to Dec 2, 2025), one per week; the original Google Docs keep their 2025 version history. Round 8 was the wrap-up period, so seven rounds settled. Bankruptcy lines and hurdles were not stated in my Round 1 and Round 6 memos, so those rounds are left out of the bankruptcy and hurdle checks.

The forward for each round is taken as that round's swap price. Settlement prices are simulated as lognormal with mean equal to the forward, which is the risk-neutral view; real-world drift would shift the probabilities. Volatility is estimated from only six price changes, which is why the Vol Sensitivity tab exists. The risk-free rate (4%) only discounts option premiums and barely moves the results.
