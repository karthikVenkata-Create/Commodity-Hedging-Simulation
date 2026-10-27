# Memo: Round 6 result + Round 7 decision (Nov 24, 2025)

Trader ID: BULLSANDBEARS7

## Round 6 result

Strategy: 20,000 float, 40,000 at swap $75, 40,000 collar (put $70 / call $95). Spot price: $225.

Spot revenue: 100,000 x 225 = $22,500,000
Swap: (75 - 225) x 40,000 = -$6,000,000
Collar (40,000 units): put payoff = max(70 - 225, 0) = 0; call payoff = max(225 - 95, 0) = 130; call loss = -130 x 40,000 = -$5,200,000
Total revenue: 22,500,000 - 6,000,000 - 5,200,000 = $11,300,000

## Round 7 decision

Choice: hedge 30,000 units using the swap at $210, use a collar on 50,000 units by buying the $200 put and selling the $240 call, and leave the remaining 20,000 units unhedged.

Rationale: I chose this combination because it gives a safer balance going into the next period. Hedging 30,000 units with the swap at $210 protects a significant portion of revenue if prices fall sharply, reducing the risk of dropping near the bankruptcy zone again.

For 50,000 units, I went with a collar because it gives us downside protection without paying a large upfront premium. The $200 put establishes a meaningful price floor, and writing the $240 call helps make it a close-to-zero-cost hedge. The trade-off is giving up upside above $240, but it keeps hedging costs low while still preventing major losses if prices fall.

I kept 20,000 units unhedged to leave some room for upside if the spot price on the delivery date ends up well above the hedge levels. This way, we're not fully capped and can still benefit from favorable market conditions. Overall, this mix reduces risk, keeps hedging expenses low, and still provides some potential for gains if the price rises.

Final decision: 20,000 float, 30,000 at swap rate of $210, 50,000 collar (put $200 / call $240).
