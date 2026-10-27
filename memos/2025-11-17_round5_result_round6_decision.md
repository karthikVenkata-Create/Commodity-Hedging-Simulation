# Memo: Round 5 result + Round 6 decision (Nov 17, 2025)

Trader ID: BULLSANDBEARS7

## Round 5 result

Strategy: 10,000 float, 30,000 at swap $56, 60,000 collar (put $45 / call $75). Spot price: $83.80.

Spot revenue: 100,000 x 83.80 = $8,380,000
Swap: (56 - 83.80) x 30,000 = -$834,000
Collar (60,000 units): put payoff = max(45 - 83.80, 0) = 0; call payoff = max(83.80 - 75, 0) = 8.80; call loss = -8.80 x 60,000 = -$528,000
Total revenue: 8,380,000 - 834,000 - 528,000 = $7,018,000

Needed to invest: $9,500,000. Bankruptcy threshold: $4,500,000.

## Round 6 decision

Choice: leave 20,000 units unhedged, hedge 40,000 units with the swap at $75, and use a collar on the remaining 40,000 units by buying the $70 put and selling the $95 call.

Rationale: I chose this mix because it feels like a balanced approach. The swap on 40,000 units gives us some guaranteed protection if prices fall, so we don't end up close to the bankruptcy zone again. For the other 40,000 units, I went with the collar because it gives us a floor without paying a big premium. The $70 put protects us if the price drops a lot, and selling the $95 call helps make the hedge basically free. The only drawback is losing upside above $95, but at least we're not spending a lot upfront.

I kept 20,000 units unhedged so that if the price goes up, we can still enjoy some of that upside instead of being completely capped. Overall, this setup keeps us safer if prices fall, avoids high hedging costs, and still lets us benefit if the market ends up doing well.

Final decision: 20,000 float, 40,000 at swap rate of $75, 40,000 collar (put $70 / call $95).
