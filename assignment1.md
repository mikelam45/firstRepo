# Assignment 1 — SuperTrend Trading Strategy (Pine Script)

## Overview

Convert the provided SuperTrend **indicator** (`SuperTrend_indicator.txt`) into a Tradeable TradingView **strategy**, then iteratively improve it with risk management and your own research-driven enhancements.

| Part | Focus | Weight |
|------|--------|--------|
| A | Base SuperTrend strategy (entries + fixed TP/SL + signal exits) | — |
| B | Trailing stop-loss mechanism | — |
| C | Original strategy modification & performance comparison | **30 marks** |

---

## Reference material

Use `SuperTrend_indicator.txt` (Pine Script v4) as the signal source. Key definitions from that script:

| Concept | Definition |
|---------|------------|
| **Buy signal** | `trend` flips from `-1` → `1` (`buySignal = trend == 1 and trend[1] == -1`) |
| **Sell signal** | `trend` flips from `1` → `-1` (`sellSignal = trend == -1 and trend[1] == 1`) |
| **ATR Period** | Default `10` (user input) |
| **ATR Multiplier** | Default `3.0` (user input) |
| **Source** | Default `hl2` |
| **ATR method** | Toggle between `atr(Periods)` (RMA) and `sma(tr, Periods)` |

Preserve SuperTrend signal logic so strategy Buy/Sell flips match the indicator under the same inputs.

---

## Common requirements (all parts)

### Platform & script type

- Language: **TradingView Pine Script** (v4 or v5; v5 preferred if you migrate)
- Script type: `strategy(...)` (not `study` / `indicator`)
- Overlay on price chart
- Plot SuperTrend lines and optional Buy/Sell markers for visual verification

### Backtesting window

- **Start date:** `2023-01-01` (use `timestamp` / strategy date filter or TradingView Strategy Tester range)
- **End date:** latest available data (state the end date used in your report)
- Document the **symbol** and **timeframe** used (e.g. BTCUSDT, 1H). Keep these consistent across Parts A–C unless you justify a change.

### Strategy properties (recommended defaults)

Document whatever you choose; example starting point:

- Initial capital: e.g. `10000`
- Order size: e.g. `% of equity` or fixed contracts (state clearly)
- Commission & slippage: enable realistic values if possible and report them
- Pyramiding: `0` (one position at a time) unless your Part C proposal requires otherwise

### Deliverables per part

1. Pine Script source code
2. Parameter table (inputs + recommended / optimized values)
3. Backtest summary (see metrics below)
4. Brief commentary: what worked, what did not, and why

### Suggested performance metrics

Report at least:

- Net profit / net profit %
- Max drawdown %
- Win rate
- Profit factor
- Number of trades
- Average trade / average win vs average loss (optional but useful)

---

## Part A — Base SuperTrend strategy

### Objective

Build a long/short SuperTrend strategy with fixed take-profit (TP), fixed stop-loss (SL), and opposite-signal exits.

### Long setup

| Action | Condition |
|--------|-----------|
| **Enter long** | When the SuperTrend **Buy** signal occurs (trend flip to bullish) |
| **Exit long** | Whichever occurs first among the following |

Exit priorities for an open long:

1. **Take profit (TP)** — user-defined (e.g. % from entry, or ATR multiple, or absolute ticks/points — choose one method and expose it as inputs)
2. **Stop loss (SL)** — user-defined (same unit system as TP for consistency)
3. **Opposite signal** — close long when SuperTrend **Sell** signal occurs

### Short setup (vice versa)

| Action | Condition |
|--------|-----------|
| **Enter short** | When the SuperTrend **Sell** signal occurs (trend flip to bearish) |
| **Exit short** | Whichever occurs first among the following |

Exit priorities for an open short:

1. **Take profit (TP)** — user-defined
2. **Stop loss (SL)** — user-defined
3. **Opposite signal** — close short when SuperTrend **Buy** signal occurs

### Required user inputs (minimum)

- SuperTrend: ATR Period, ATR Multiplier, Source, ATR method toggle (as in the indicator)
- Risk: TP distance, SL distance (with clear units: `%` recommended)
- Optional toggles: enable long / enable short; show signals; highlighting

### Tasks

1. Implement the strategy as specified above.
2. Backtest from **2023-01-01**.
3. Tune parameters (at least ATR Period, Multiplier, TP, SL) and **propose a recommended parameter set** with the best overall performance you find.
4. Summarize results and justify why that set is preferred (not only highest net profit — consider drawdown and trade count).

---

## Part B — Trailing stop-loss

### Objective

Extend Part A with a **trailing stop-loss (trailing SL)** and expose proper user inputs for the trailing mechanism.

### Trailing SL requirements

Implement a clear trailing model. Examples of acceptable designs (pick one and document it):

- Trail by a fixed **%** behind the best favorable price since entry
- Trail by an **ATR multiple** behind the best favorable price
- Trail using the SuperTrend line itself as a dynamic stop (if used, still expose offsets / activation rules as inputs)

### Required trailing inputs (illustrative — adapt to your design)

| Input | Purpose |
|-------|---------|
| Enable trailing SL | On/Off |
| Trail activation | Optional: start trailing only after price moves X% / ATR in favor |
| Trail offset / distance | How far the stop trails the extreme |
| Trail step (optional) | Minimum stop movement increment |

Behavior notes:

- When trailing is enabled, clarify how it interacts with the **fixed SL** from Part A (replace fixed SL, or use the tighter of fixed vs trailing).
- Opposite SuperTrend signal exit should still be available (or justify if you disable it).
- TP may remain as in Part A; state whether trailing and TP can both be active.

### Tasks

1. Modify the strategy to include trailing SL with documented inputs.
2. Backtest from **2023-01-01** under the same symbol/timeframe as Part A.
3. Optimize trailing-related parameters (and revisit core SuperTrend / TP settings if needed).
4. Summarize findings and present the **optimized parameter set** you discovered, comparing vs Part A (same metrics).

---

## Part C — Proposed modification (30 marks)

### Objective

Propose and implement **your own** improvement to the trading strategy. Marks favor clear rationale, correct implementation, fair backtesting, and evidence of improvement (or honest analysis if results worsen).

### Allowed directions (examples — not exhaustive)

- Add confirming indicators (e.g. EMA/SMA trend filter, RSI, MACD, volume, ADX)
- Restrict entries to higher-timeframe trend alignment
- Session / volatility filters (e.g. only trade when ATR is above a threshold)
- Partial take-profit / scaled exits
- Time-based exits (max bars in trade)
- Regime filter (only long in bull regimes, only short in bear regimes)

### Tasks

1. **Propose** the modification: what you add/change and why (hypothesis).
2. Implement it on top of Part B (or clearly state the baseline you extend).
3. Backtest from **2023-01-01** with the same evaluation setup.
4. Summarize findings and **illustrate possible performance improvement** vs Parts A and B (tables/charts from Strategy Tester are fine).
5. Discuss limitations (overfitting risk, sample period bias, market dependence).

### Suggested report structure for Part C

1. Hypothesis  
2. Design & new inputs  
3. Results vs A/B  
4. Recommended final parameter set  
5. Risks & next steps  

---

## Submission checklist

- [ ] Part A Pine Script + recommended parameters + backtest summary  
- [ ] Part B Pine Script (trailing SL) + optimized parameters + comparison to A  
- [ ] Part C proposal write-up + Pine Script + comparison showing improvement analysis  
- [ ] Symbol, timeframe, date range, commission/slippage assumptions documented  
- [ ] Buy/Sell logic still consistent with `SuperTrend_indicator.txt` (unless Part C intentionally changes signals — if so, explain)

---

## Notes

- “Best performance” is not only maximum profit: prefer a balanced profile (return vs max drawdown vs trade quality).
- Avoid curve-fitting to a handful of trades; prefer parameter regions that remain stable under small perturbations.
- If you migrate from Pine v4 → v5, keep signal equivalence with the reference indicator and note any intentional differences.
