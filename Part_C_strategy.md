# Part C Strategy — Enhanced SuperTrend with EMA Regime + Bollinger Bands

Propose a modification on the trading strategy by adding EMA trend regime filters and Bollinger Band mean-reversion entries, while using SuperTrend as the directional filter and trailing exit.

---

## Enhanced Long Strategy (Golden Cross + BB)

In Bitcoin, a Golden Cross (50 EMA crossing above 200 EMA) often happens after a massive rally, meaning you are entering late. The Bollinger Bands fix this by forcing you to buy the first major pullback after the cross.

### The Condition

50 EMA is above 200 EMA (Bullish Regime).

### The Filter

Supertrend must be Green.

### The Enhancement (BB Mean Reversion Entry)

- Do not buy the moment the Golden Cross happens.
- Wait for BTC price to pull back and touch or close below the Bollinger Band Middle Line (20 SMA Baseline).
- **Advanced Trigger:** For an even better risk-to-reward ratio, wait for the price to drop to the Lower Bollinger Band while the 50/200 EMA remains bullish.

### The Exit

Hold the position until the Supertrend turns Red (Trailing Stop).

---

## Enhanced Short Strategy (Death Cross + BB)

During crypto bear markets, Bitcoin suffers violent "dead cat bounces" (sharp, temporary relief rallies). The Bollinger Bands allow you to short the exact top of these bounces.

### The Condition

50 EMA is below 200 EMA (Bearish Regime).

### The Filter

Supertrend must be Red.

### The Enhancement (BB Mean Reversion Entry)

- Do not short the moment the Death Cross happens.
- Wait for BTC price to rally upward and touch or close above the Bollinger Band Middle Line (20 SMA Baseline) or the Upper Bollinger Band.
- Enter your short position at this overextended high.

### The Exit

Hold the position until the Supertrend turns Green (Trailing Stop).
