# Part C Strategy — Enhanced SuperTrend with EMA Regime + Bollinger Bands

## 1. Hypothesis

In Bitcoin, a **Golden Cross** (50 EMA crossing above 200 EMA) often happens *after* a large rally, so buying the cross itself is late. A **Death Cross** often happens after a crash, so shorting the cross itself is late and gets trapped in dead-cat bounces.

**Proposal:** Keep SuperTrend as the **trend filter + trailing exit**, but:

1. Trade only in the correct **EMA regime** (50 vs 200).
2. Enter on a **Bollinger Band pullback / bounce** (mean reversion into the trend), not on the EMA cross event itself.

This should improve **entry price (R:R)** vs raw SuperTrend flip entries (Parts A/B), while exits remain trend-following via SuperTrend color change.

**Baseline extended:** Part B SuperTrend logic (same ATR bands / Buy=green flip, Sell=red flip). Part C **changes when entries are allowed**; exit is SuperTrend flip (trailing-style), with optional fixed TP/SL inputs for risk control.

---

## 2. Indicator definitions (must match these formulas)

| Component | Definition | Default |
|-----------|------------|---------|
| Fast EMA | `EMA(close, emaFast)` | **50** |
| Slow EMA | `EMA(close, emaSlow)` | **200** |
| Bullish regime | `emaFast > emaSlow` (state, not only the cross bar) | — |
| Bearish regime | `emaFast < emaSlow` | — |
| BB Basis (middle) | `SMA(close, bbLength)` | **20** |
| BB StdDev | `stdev(close, bbLength)` | — |
| BB Upper | `basis + bbMult * stdev` | mult **2.0** |
| BB Lower | `basis - bbMult * stdev` | mult **2.0** |
| SuperTrend | Same as `SuperTrend_indicator.txt` | ATR Period **10**, Mult **3.0**, source **hl2**, RMA ATR |
| SuperTrend Green | `trend == 1` | — |
| SuperTrend Red | `trend == -1` | — |
| SuperTrend turns Red | `sellSignal` = was green, now red | exit long |
| SuperTrend turns Green | `buySignal` = was red, now green | exit short |

> **Important:** Regime uses **state** (`50 > 200`), not only the single bar of the Golden/Death Cross. After the cross, wait for BB pullback/bounce while the regime remains valid.

---

## 3. Enhanced Long Strategy (Golden Cross regime + BB)

### Idea

Golden Cross often marks a late entry after a rally. Bollinger Bands force buying the **first major pullback** while the bullish regime and SuperTrend green remain intact.

### Condition (regime)

- `EMA(50) > EMA(200)` → **Bullish regime**

### Filter

- SuperTrend must be **Green** (`trend == 1`)

### Enhancement — BB mean-reversion entry

**Do not** buy on the Golden Cross bar alone.

Wait for a pullback:

| Mode | Long entry trigger (all must be true) |
|------|----------------------------------------|
| **Standard** (`bbEntryMode = Middle`) | Bullish regime **AND** SuperTrend green **AND** price **touches or closes at/below** BB Middle (`low <= basis` or `close <= basis`) |
| **Advanced** (`bbEntryMode = Lower`) | Bullish regime **AND** SuperTrend green **AND** price **touches or closes at/below** BB Lower (`low <= lower` or `close <= lower`) |

**Advanced trigger** aims for better R:R (deeper discount) but fewer trades.

### Exit (long)

- Hold until SuperTrend **turns Red** (`sellSignal`) → close long (SuperTrend trailing exit).
- Optional: also honor fixed TP%/SL% if enabled (see inputs).

---

## 4. Enhanced Short Strategy (Death Cross regime + BB)

### Idea

In bear markets, BTC often prints violent dead-cat bounces. Short the **overextended rally** into BB middle/upper while the bearish regime and SuperTrend red remain intact.

### Condition (regime)

- `EMA(50) < EMA(200)` → **Bearish regime**

### Filter

- SuperTrend must be **Red** (`trend == -1`)

### Enhancement — BB mean-reversion entry

**Do not** short on the Death Cross bar alone.

Wait for a bounce:

| Mode | Short entry trigger (all must be true) |
|------|----------------------------------------|
| **Standard** (`bbEntryMode = Middle`) | Bearish regime **AND** SuperTrend red **AND** price **touches or closes at/above** BB Middle (`high >= basis` or `close >= basis`) |
| **Advanced** (`bbEntryMode = Upper`) | Bearish regime **AND** SuperTrend red **AND** price **touches or closes at/above** BB Upper (`high >= upper` or `close >= upper`) |

Enter the short at this overextended high.

### Exit (short)

- Hold until SuperTrend **turns Green** (`buySignal`) → close short.
- Optional: also honor fixed TP%/SL% if enabled.

---

## 5. Proper user inputs for Part C (Pine Script)

Expose **all** of the following as inputs (grouped). Defaults are the recommended starting set for BTCUSD backtests from 2023-01-01.

### 5.1 SuperTrend (same family as Parts A/B)

| Input ID | UI label | Type | Default | Notes |
|----------|----------|------|---------|--------|
| `atrPeriod` | ATR Period | int | `10` | Match indicator |
| `stSrc` | SuperTrend Source | source | `hl2` | Match indicator |
| `stMult` | ATR Multiplier | float | `3.0` | Match indicator |
| `changeATR` | Use RMA ATR | bool | `true` | Unchecked = SMA of TR |

### 5.2 EMA regime

| Input ID | UI label | Type | Default | Notes |
|----------|----------|------|---------|--------|
| `emaFast` | Fast EMA Length | int | `50` | Golden/Death fast leg |
| `emaSlow` | Slow EMA Length | int | `200` | Golden/Death slow leg |
| `useEmaRegime` | Require EMA regime | bool | `true` | If false, BB+ST only (debug) |

### 5.3 Bollinger Bands

| Input ID | UI label | Type | Default | Notes |
|----------|----------|------|---------|--------|
| `bbLength` | BB Length | int | `20` | Middle = SMA baseline |
| `bbMult` | BB StdDev Mult | float | `2.0` | Classic BB |
| `bbEntryMode` | BB Entry Mode | string | `Middle` | Options: `Middle` \| `Outer` |
| `bbTouchRule` | Touch rule | string | `Wick or Close` | Options: `Wick or Close` \| `Close only` |

**Mode mapping**

- `Middle` → long uses BB middle; short uses BB middle (standard).
- `Outer` → long uses **Lower** band (advanced); short uses **Upper** band (advanced).

**Touch rule**

- `Wick or Close` (recommended): long if `low <= level` OR `close <= level`; short if `high >= level` OR `close >= level`.
- `Close only`: use close vs level only (fewer, cleaner signals).

### 5.4 Trade direction & one-shot entry control

| Input ID | UI label | Type | Default | Notes |
|----------|----------|------|---------|--------|
| `enableLong` | Enable Long | bool | `true` | |
| `enableShort` | Enable Short | bool | `true` | Set false for long-only BTC tests |
| `entryOncePerRegime` | One entry per pullback cycle | bool | `true` | Avoid re-buying every bar while price stays below middle |
| `requireStAlign` | Require SuperTrend color filter | bool | `true` | Must be green for long / red for short |

**`entryOncePerRegime` behavior (required for “proper” inputs)**

- After a long entry, **do not** enter long again until price has recovered **above** BB middle (reset), then a new pullback qualifies.
- After a short entry, **do not** enter short again until price has fallen **below** BB middle (reset), then a new bounce qualifies.
- This implements “buy the pullback / short the bounce” once per cycle, not every bar in the zone.

### 5.5 Exits

| Input ID | UI label | Type | Default | Notes |
|----------|----------|------|---------|--------|
| `exitOnStFlip` | Exit on SuperTrend flip | bool | `true` | Primary exit (trailing via ST) |
| `useFixedTP` | Enable fixed Take Profit % | bool | `false` | Optional; OFF so ST can trail |
| `tpPerc` | Take Profit % | float | `35.0` | Used only if `useFixedTP` |
| `useFixedSL` | Enable fixed Stop Loss % | bool | `false` | Optional hard stop |
| `slPerc` | Stop Loss % | float | `10.0` | Used only if `useFixedSL` |

### 5.6 Strategy / backtest properties (document in report)

| Property | Recommended Part C value |
|----------|--------------------------|
| Symbol | BTCUSD (same as Parts A/B) |
| Timeframe | Same as A/B (e.g. 4H) |
| Initial capital | `1000000` |
| Order size | 100% of equity (or same as A/B) |
| Commission | 0.04% |
| Slippage | 2 ticks |
| Pyramiding | 0 |
| Backtest start | **2023-01-01** |
| Date filter input | `useDateFilter=true`, `startDate=2023-01-01` |

---

## 6. Exact entry / exit boolean logic (for implementation)

Define:

```text
bullRegime = ema50 > ema200
bearRegime = ema50 < ema200
stGreen    = trend == 1
stRed      = trend == -1

bbBasis, bbUpper, bbLower = Bollinger(close, bbLength, bbMult)

longLevel  = bbBasis          if bbEntryMode == Middle else bbLower
shortLevel = bbBasis          if bbEntryMode == Middle else bbUpper

longTouch  = (low <= longLevel or close <= longLevel)    // or close-only variant
shortTouch = (high >= shortLevel or close >= shortLevel)

longEntry  = enableLong and bullRegime and stGreen and longTouch and longCycleArmed
shortEntry = enableShort and bearRegime and stRed and shortTouch and shortCycleArmed

longExit   = sellSignal     // SuperTrend turns Red
shortExit  = buySignal      // SuperTrend turns Green
```

**Cycle arming (when `entryOncePerRegime=true`)**

```text
// Long cycle: armed after price reclaims above BB middle; disarmed on long entry
on longEntry  -> longCycleArmed = false
on close > bbBasis -> longCycleArmed = true   // reset after recovery

// Short cycle: armed after price loses BB middle; disarmed on short entry
on shortEntry -> shortCycleArmed = false
on close < bbBasis -> shortCycleArmed = true
```

If `entryOncePerRegime=false`, treat `longCycleArmed` / `shortCycleArmed` as always true (not recommended).

---

## 7. Recommended default parameter set (Part C)

| Group | Parameter | Value |
|-------|-----------|-------|
| SuperTrend | ATR Period / Mult / Source | 10 / 3.0 / hl2 |
| EMA | Fast / Slow | 50 / 200 |
| BB | Length / Mult / Mode / Touch | 20 / 2.0 / **Middle** / Wick or Close |
| Direction | Long / Short | true / true (or long-only for BTC bull bias) |
| Entry control | One entry per cycle | **true** |
| Exit | SuperTrend flip | **true** |
| Optional TP/SL | Fixed TP/SL | **false** / false |
| Capital | Initial / size | 1,000,000 / 100% equity |
| Window | From | 2023-01-01 |

**Sensitivity tests to report**

1. `bbEntryMode`: Middle vs Outer  
2. Long-only vs long+short  
3. `entryOncePerRegime` on vs off  
4. Optional fixed SL 10% on/off (risk control vs pure ST exit)

---

## 8. What changed vs Parts A / B

| Topic | Part A / B | Part C |
|-------|------------|--------|
| Entry | SuperTrend Buy/Sell flip | BB pullback/bounce **inside** EMA regime + ST color filter |
| EMA | Not used (A) / optional in experiments | **Required regime** 50/200 |
| BB | Not used | **Entry timing** |
| Exit | TP/SL and/or opposite ST signal / trailing | Primary: **ST color flip**; optional fixed TP/SL |
| Goal | Trade every ST flip | Trade **pullbacks in trend** for better R:R |

---

## 9. Part C deliverables checklist

- [ ] Pine Script strategy implementing the inputs in §5  
- [ ] Backtest from 2023-01-01 on same symbol/TF as A/B  
- [ ] Table: Part C vs A vs B (net profit %, max DD %, win rate, profit factor, # trades)  
- [ ] Recommended final parameter set (§7, tuned if needed)  
- [ ] Limitations: fewer trades; lagging EMAs; BB whipsaw in chop; BTC bull-sample bias 2023–2024  

---

## 10. Risks / limitations

- **Fewer trades** than raw SuperTrend flips — statistics may be noisier.  
- **EMA lag:** regime can stay bullish into a deep correction.  
- **Outer band mode** may miss trends that never tag the lower/upper band.  
- **Overfitting** if BB length/mult are heavily tuned to one BTC period.  
- Dead-cat shorts still risky if SuperTrend stays red too long into a squeeze — optional fixed SL mitigates this.
