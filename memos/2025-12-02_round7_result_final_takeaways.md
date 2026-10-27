# Memo: Round 7 result + final takeaways (Dec 2, 2025)

Trader ID: BULLSANDBEARS7

## Round 7 result

Strategy: 20,000 float, 30,000 at swap $210, 50,000 collar (put $200 / call $240). Spot price: $74.

Spot revenue: 100,000 x 74 = $7,400,000
Swap: (210 - 74) x 30,000 = $4,080,000
Collar (50,000 units): put payoff = max(200 - 74, 0) = 126; call payoff = max(74 - 240, 0) = 0; collar profit = 126 x 50,000 = $6,300,000
Total revenue: 7,400,000 + 4,080,000 + 6,300,000 = $17,780,000

Total revenue < $20,000,000, so no investment NPV. Total revenue > $5,000,000, so no bankruptcy cost.

## Final takeaways

This round showed how important downside protection is when prices crash suddenly. The spot price dropped to $74, which would have caused massive losses if most of the position was left unhedged. However, because I used a mix of a swap at $210 and a collar with a $200 put, my losses were limited and I was still able to make solid revenue. The unhedged portion did lose money, but the hedged positions helped balance everything out and, most importantly, kept me away from the bankruptcy zone.

Looking at the entire hedging game as a whole, I learned that no single hedge is perfect in every situation. In some rounds, like earlier ones with higher prices, collars limited upside due to the call, but in a round like this one with a price crash, the put was extremely valuable. The game showed me that using a combination of swaps, collars, and some unhedged exposure helps manage risk better than putting everything into one strategy. Overall, this taught me that hedging is about reducing uncertainty and protecting the downside, not trying to perfectly predict prices.
