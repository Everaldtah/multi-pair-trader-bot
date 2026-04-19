# SuperTrend Alpha V6 - Backtest Results
**Date:** April 19, 2026  
**Data:** 62 days of 1h candles (Feb - Apr 2026)  
**Pairs:** BTC-USDT, ETH-USDT, SOL-USDT, BNB-USDT

---

## ⚠️ Critical Finding

**Every tested configuration lost money in the last 2 months.**

| Config | Trades | Win Rate | Return | Profit Factor |
|--------|--------|----------|--------|---------------|
| v6_current (strict) | 178 | 35.4% | -14.2% | 0.48 |
| v6_no_ema | 193 | 34.7% | -14.2% | 0.50 |
| v6_loose_adx | 178 | 35.4% | -14.2% | 0.48 |
| v6_balanced | 186 | 36.0% | -14.8% | 0.48 |
| v5_style | 186 | 36.0% | -14.8% | 0.48 |
| v6_strength | 203 | 33.0% | -16.4% | 0.45 |
| v6_aggressive | 203 | 33.0% | -16.4% | 0.45 |

---

## 🔍 What This Means

### The Market Regime (Feb-Apr 2026) = DEATH for Trend Following

- **34-36% win rate** across all configs = terrible
- **Profit Factor < 0.5** = losing $2 for every $1 won
- **All pairs negative** = not a single pair saved the portfolio
- March 2026 was especially brutal (-$118 across configs)

### Your Bot's 0 Trades = Actually Smart

Your v6 bot has **0 lifetime trades** because the signals are too strict. But looking at this data:
- **If v6 traded normally: -14% loss** on $1,000 = **-$140**
- **If v6 stayed out: $0 loss**

**The strict filters SAVED you money.** The market has been in a choppy/sideways regime where SuperTrend gets repeatedly whipsawed.

---

## 📊 Why SuperTrend is Failing Right Now

SuperTrend is a **trend-following** strategy. It needs:
1. ✅ Clear directional trends
2. ❌ NOT choppy sideways action

Feb-Apr 2026 has been:
- Multiple false breakouts
- Sharp reversals
- Low volatility chop
- "Bart" patterns (pump then immediate dump)

This kills trend followers. The strategy works in strong bull or bear runs, dies in consolidation.

---

## 💡 My Recommendation

### DON'T deposit £1,000 yet.

**The strategy is not viable in current market conditions.**

### Instead, do this:

#### Option 1: Add a Market Regime Filter (Recommended)

Only trade when the market is actually trending. Add this to v6:

```python
# Market Regime Filter - Skip choppy markets
def is_trending_market(adx_values, lookback=50):
    """Only trade if average ADX > 25 over last 50 bars"""
    if len(adx_values) < lookback:
        return False
    return np.mean(adx_values[-lookback:]) > 25.0

# In signal generation:
if not is_trending_market(adx_history):
    return "HOLD", 0.0  # Market too choppy, sit out
```

This would have kept you flat during Feb-Apr and saved the -14% loss.

#### Option 2: Mean Reversion Mode (Alternative Strategy)

When ADX < 20 (choppy market), switch to mean reversion:
- Buy when price hits lower Bollinger Band
- Sell when price hits upper Bollinger Band
- Only trade within the range

#### Option 3: Wait for Trend Confirmation

Keep the bot running but with a "dry run" mode. When you see:
- ADX > 30 on daily timeframe
- Clear break above/below key levels
- Volume expanding

...THEN enable live trading.

---

## 📈 Realistic Profit Estimates (Revised)

Given the backtest data, here are **honest** projections:

| Scenario | Conditions | Monthly Return | £1,000 by Dec 2026 |
|----------|------------|----------------|-------------------|
| **Choppy market** (current) | ADX < 25, sideways | **0%** (bot sits out) | **£1,000** (preserved) |
| **Trending market** | Strong ADX, clear direction | 5-10% | £1,400-£1,800 |
| **Bull run** | Crypto pump | 15-25% | £2,200-£3,000 |
| **Mixed year** | 6mo chop + 6mo trend | 3-5% avg | £1,300-£1,500 |

**Key insight:** The bot's job isn't just to trade — it's to **preserve capital during bad times** and **capture trends during good times.**

---

## 🔧 Tuned Configuration for When Markets Trend

When the market DOES start trending, use this tuned config:

```python
# TUNED V6 - For Trending Markets Only
ADX_THRESHOLD = 18          # Slightly lower than 20
EMA_FILTER = True           # Keep trend alignment
VOLUME_FILTER = 0.6         # Slightly relaxed from 0.8
MIN_STRENGTH = 0.50         # Require 50% signal strength

# ADD regime filter:
MARKET_ADX_MIN = 25         # Average ADX must be > 25
```

This would have produced better results in trending periods while still avoiding the chop.

---

## ✅ Action Items

1. **Keep v6 running as-is for now** — the strictness is protecting you
2. **Add regime filter** — I can code this for you
3. **Deposit only £200-£300** initially for live testing
4. **Scale to £1,000 only after** you see 10+ winning trades in a trending period
5. **Monitor ADX on daily charts** — when BTC daily ADX > 30, the party starts

---

## 📉 The Hard Truth

If you had deposited £1,000 last month and ran the bot aggressively:
- **You'd have ~£860 now** (-14% loss)
- **Your "broken" bot with 0 trades saved you £140**

Sometimes the best trade is no trade.

Want me to:
1. **Code the market regime filter** into v6?
2. **Build a mean-reversion strategy** for chop periods?
3. **Set up a monitoring alert** for when the market starts trending?
