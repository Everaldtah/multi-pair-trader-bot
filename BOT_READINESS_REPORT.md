# Multi-Pair Trading Bot v5.0 — Readiness Assessment Report
## Deposit Size: £1,000 GBP (~$1,350 USD @ 1.35 GBP/USD)
## Generated: 2026-04-19

---

## EXECUTIVE SUMMARY: NOT READY FOR LIVE DEPLOYMENT

**Recommendation: DO NOT DEPOSIT. Paper trade only until strategy edge is proven.**

The walk-forward backtest, Monte Carlo simulation, and Kelly analysis all confirm the current strategy has **negative expected value**. Deploying £1,000 would likely result in a 25-50% drawdown within months.

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Out-of-sample Profit Factor | 0.55 | > 1.0 required | FAIL |
| Win Rate | 30.1% | > 33% breakeven | FAIL |
| Monte Carlo Mean Final Capital | $647 | > $1,350 start | FAIL |
| Probability of Profit | 0.0% | > 50% desired | FAIL |
| Kelly Fraction | -24.5% | > 0 required | FAIL |
| Mean Max Drawdown | 52.8% | < 20% desired | FAIL |
| Risk of Ruin (adverse) | 12.6% | < 5% required | FAIL |

---

## 1. METHODOLOGY

### 1.1 Data
- **Source:** KuCoin public API
- **Pairs:** ETH, BTC, SOL, LINK, AVAX, DOT, UNI, AAVE, ATOM, ADA, DOGE, XRP (MATIC delisted)
- **Timeframe:** 1-hour candles
- **Period:** 14 months (10,074 candles per pair)
- **Fees:** 0.1% maker/taker + slippage 0.05% (liquid) / 0.15% (illiquid)

### 1.2 Walk-Forward Design
- **Training window:** 6 months (4,320 candles)
- **Test window:** 2 months (1,440 candles)
- **Step:** 2 months
- **Windows tested:** 3 out-of-sample periods
- **Total out-of-sample trades:** 1,513

### 1.3 Strategy Replicated
The backtest exactly replicates the bot's v5.0 ensemble logic:
- RSI (20% weight), EMA crossover (20%), MFI (15%), MACD (15%)
- Bollinger Bands (15%), SuperTrend (10%), ADX modifier (5%)
- Buy threshold: composite >= 0.55
- Sell threshold: composite <= 0.35
- Stop loss: 1.5%, Take profit: 3.0%
- Position sizing: 10% of capital (3-15% range)
- Max 5 concurrent positions

---

## 2. WALK-FORWARD BACKTEST RESULTS

### 2.1 Aggregate Performance
| Window | Trades | Win Rate | Avg P&L | Final Capital | Max DD |
|--------|--------|----------|---------|---------------|--------|
| 1 | 503 | 30.8% | -0.73% | $1,022.84 | 24.7% |
| 2 | 540 | 30.6% | -0.69% | $1,004.62 | 27.8% |
| 3 | 470 | 28.7% | -0.77% | $1,016.91 | 26.2% |
| **Total** | **1,513** | **30.1%** | **-0.73%** | **~$1,014** | **~26%** |

### 2.2 Per-Pair Performance (ALL LOSING)
| Pair | Trades | Win Rate | Profit Factor | Gross P&L |
|------|--------|----------|---------------|-----------|
| ETH-USDT | 172 | 29.7% | 0.56 | -$111.74 |
| BTC-USDT | 124 | 32.3% | 0.57 | -$69.40 |
| SOL-USDT | 196 | 30.1% | 0.58 | -$115.00 |
| LINK-USDT | 188 | 33.5% | 0.64 | -$95.56 |
| AVAX-USDT | 183 | 27.9% | 0.52 | -$127.75 |
| DOT-USDT | 142 | 34.5% | 0.68 | -$68.22 |
| UNI-USDT | 130 | 25.4% | 0.39 | -$147.46 |
| AAVE-USDT | 96 | 35.4% | 0.69 | -$39.41 |
| ATOM-USDT | 104 | 32.7% | 0.60 | -$58.85 |
| ADA-USDT | 66 | 21.2% | 0.33 | -$65.21 |
| DOGE-USDT | 54 | 25.9% | 0.41 | -$51.01 |
| XRP-USDT | 58 | 22.4% | 0.39 | -$56.02 |

### 2.3 Market Context
The 14-month backtest period included a significant crypto bear market:
- BTC: -21.3% total return, 52.5% peak drawdown
- ETH: -17.7% total return, 72.1% peak drawdown
- SOL: -48.9% total return, 73.4% peak drawdown

A long-only strategy without regime awareness is structurally disadvantaged in such conditions.

---

## 3. CORRELATION ANALYSIS

Average pairwise correlation of trade P&L: **0.000** (effectively uncorrelated)

**Interpretation:** Positions across pairs do not hedge each other. The multi-pair approach provides diversification of opportunity but not risk reduction. Losses in one pair are independent of losses in another.

---

## 4. MONTE CARLO SIMULATION (10,000 Runs)

### 4.1 Method
- Block bootstrap with block size = 25 trades (preserves streak autocorrelation)
- Dynamic position sizing (10% of current capital per trade)
- Starting capital: $1,350

### 4.2 Results
| Metric | Value |
|--------|-------|
| Mean final capital | **$647** |
| Median final capital | **$642** |
| 5th percentile | **$518** |
| 95th percentile | **$796** |
| Worst case | **$377** |
| Probability of profit | **0.0%** |
| Probability of doubling | **0.0%** |
| Mean max drawdown | **52.8%** |
| Worst max drawdown | **72.3%** |
| Ruin probability (<$100) | **0.0%** |

**Verdict:** The strategy is expected to lose approximately half the deposit over the simulation horizon. No run was profitable.

---

## 5. SENSITIVITY ANALYSIS

### 5.1 Execution Drag (+30% friction)
Simulating worse-than-expected slippage, wider spreads, or API lag:
- Mean final capital: **$299**
- Ruin probability: **0.0%**

### 5.2 Adverse Oversampling (2x loss frequency)
Simulating a period where losses cluster more than historical average:
- Mean final capital: **$125**
- Ruin probability: **12.6%**

**Verdict:** The strategy is fragile. Even mild degradation in execution or an adverse market regime dramatically accelerates losses.

---

## 6. KELLY CRITERION

| Metric | Value |
|--------|-------|
| Win probability (p) | 30.1% |
| Avg win (b units) | 2.97% |
| Avg loss | -2.32% |
| Payoff ratio (b) | 1.28 |
| Full Kelly fraction | **-24.46%** |
| Half Kelly | -12.23% |
| Quarter Kelly | -6.11% |

**Recommended position size: 0%**

A negative Kelly fraction means the strategy has mathematically negative expected value. No position sizing adjustment can fix this — the signal generation itself is flawed.

---

## 7. PARAMETER OPTIMIZATION

15 configurations were tested, including:
- Higher buy thresholds (0.60, 0.65, 0.70)
- Trend-only filtering (EMA9 > EMA21)
- ADX minimum thresholds (25)
- Different R:R ratios (2:1, 4:2, 5:2)
- Adjusted indicator weights
- Regime filters (BTC > 200 EMA)

**Best result:** Profit Factor 0.61 (still below 1.0 breakeven)
**Conclusion:** No parameter tweak within the current ensemble architecture produces a profitable edge.

---

## 8. ROOT CAUSE ANALYSIS

### 8.1 Why the Strategy Fails
1. **Indicator salad:** Combining 7 lagging indicators with fixed weights creates a "consensus" signal that is neither trend-following nor mean-reversion. It is noise.
2. **No regime awareness:** The bot buys in bear markets, downtrends, and high-volatility collapses.
3. **Wrong R:R for win rate:** 3% TP / 1.5% SL requires 33%+ win rate. Actual win rate is 30%.
4. **Mean-reversion hurts in trends:** RSI, MFI, and BB all suggest "oversold" during sustained dumps.
5. **Fee drag:** 0.3% round-trip cost on 1,513 trades = ~$600 in friction alone.

### 8.2 What Would Actually Help
1. **Market regime filter:** Only trade when BTC is above its 200 EMA on the daily or 4h timeframe.
2. **Directional consistency:** Require ALL trend indicators to align (EMA, MACD, SuperTrend) before entry.
3. **Volume confirmation:** Require above-average volume on entry candle.
4. **Higher R:R:** 5% TP / 2% SL (2.5:1) reduces breakeven win rate to 29%.
5. **Dynamic position sizing:** Reduce size when recent trades are losing.
6. **Consider short capability:** In confirmed bear regimes, invert signals for short entries.

---

## 9. RECOMMENDATIONS

### 9.1 Immediate Actions (DO NOT DEPOSIT)
1. **Keep the £1,000 in your wallet.** Do not allocate to this bot.
2. **Switch to paper trading mode.** Run the bot with zero real capital.
3. **Track paper performance for 30 days minimum.** Require 100+ paper trades with PF > 1.2 before going live.

### 9.2 Bot Upgrades Required
1. Add BTC regime filter (200 EMA)
2. Increase default buy threshold to 0.65
3. Adjust TP/SL to 5% / 2%
4. Add volume confirmation
5. Add paper trade mode toggle
6. Improve logging with per-trade P&L tracking
7. Add daily/weekly performance reports
8. Make indicator weights configurable via config file

### 9.3 Alternative Strategies to Test
1. **Pure momentum:** Buy on 1h close above 20 EMA with volume spike, trailing stop.
2. **Mean reversion (range-bound only):** Buy oversold only when BTC is in a 30-day range (ADX < 20).
3. **Breakout:** Buy on 24h high breakout with volume confirmation.

---

## 10. CONCLUSION

The Multi-Pair Bot v5.0, as currently configured, is **not ready for live capital**. The mathematical expectation is negative. A £1,000 deposit has a ~0% probability of profit and an expected final balance of ~$650 based on 14 months of historical data.

The codebase is well-structured and the risk management framework (stop losses, max drawdown limits, position caps) is sound. However, the signal generation layer requires a fundamental redesign before any capital should be risked.

**Recommended path forward:**
1. Implement the suggested upgrades
2. Paper trade for 30 days
3. Re-run this analysis on new paper trade data
4. Only go live after achieving PF > 1.2 on 100+ out-of-sample trades

---

*Report generated by Hermes Agent — Multi-Pair Bot Readiness Assessment*
*Data: KuCoin 1h OHLCV, 14 months, 12 pairs, 1,513 out-of-sample trades*
*Simulation: 10,000 Monte Carlo runs with block bootstrap*
