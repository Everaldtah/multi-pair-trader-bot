# Architecture Deep Dive

This document explains the design decisions, signal algorithms, and code
organization of the multi-pair trading bot.

---

## Problem Statement

**Why move from single-pair to multi-pair trading?**

The v4 bot traded only ETH-USDT. During April 12-13, 2026, ETH entered a chop
zone — moving sideways between $1,600-$1,750 with no clear trend:

- RSI oscillated between 18 and 72
- MACD histogram was mostly negative
- EMA trend kept flipping between bullish and neutral

The bot correctly **avoided bad trades** — disciplined exit logic prevented
losses. But the bot sat in cash for hours, missing opportunities elsewhere.

**The solution**: Trade 12 pairs simultaneously. When ETH chops, maybe SOL
trends. When BTC consolidates, perhaps LINK breaks out. Diversification
improves opportunity capture without increasing per-trade risk.

---

## Core Architecture

### Async Design

The bot uses `asyncio` for concurrent operations:

```python
# Each pair analyzed concurrently
tasks = [analyze_pair(client, symbol) for symbol in watchlist]
analyses = await asyncio.gather(*tasks)
```

This prevents blocking on API calls — KuCoin API latency (100-500ms) would
slow down sequential analysis of 12 pairs.

### State Management

Portfolio state is tracked in memory with optional persistence:

```python
positions = {}  # symbol -> {entry_price, size, entry_time}
available_capital = SIMULATED_CAPITAL
total_pnl = 0
```

No database required — state is reconstructed from logs if needed.

### Signal Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  KuCoin API │────▶│   Klines    │────▶│ Indicators  │────▶│  Composite  │
│  (price)    │     │  (1h/24h)   │     │  (RSI/EMA)  │     │   Score     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
                                                          ┌─────────────────┐
                                                          │  BUY/HOLD/SELL  │
                                                          └─────────────────┘
```

---

## Signal Algorithms

### RSI (Relative Strength Index)

```python
def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = deltas[deltas > 0]
    losses = -deltas[deltas < 0]
    
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

**Interpretation**:
- `< 30` = Oversold → potential buy
- `> 70` = Overbought → potential sell
- `30-70` = Neutral → no signal

### EMA (Exponential Moving Average)

EMA9 vs EMA21 crossover confirms trend direction:
- EMA9 > EMA21 = Uptrend
- EMA9 < EMA21 = Downtrend

The EMA formula applies more weight to recent prices:
```
EMA_today = Price_today × k + EMA_yesterday × (1 - k)
where k = 2 / (period + 1)
```

### Composite Scoring (v4.1)

```python
score = 0.5  # Neutral baseline

# RSI component (+0.2 if oversold, -0.2 if overbought)
if rsi < 30: score += 0.2
elif rsi > 70: score -= 0.2

# EMA trend (+0.15 if uptrend, -0.15 if downtrend)
if ema_fast > ema_slow: score += 0.15
else: score -= 0.15

# Volume confirmation (+0.1 if >1.5x average)
if volume_ratio > 1.5: score += 0.1

# Signal thresholds
if score >= 0.7: signal = "BUY"
elif score <= 0.3: signal = "SELL"
else: signal = "HOLD"
```

### v5 Ensemble (Advanced)

The v5 bot uses 7 indicators with weighted scoring:

```python
SIGNAL_WEIGHTS = {
    "rsi": 0.25,        # Momentum
    "ema": 0.25,        # Trend
    "macd": 0.20,       # Momentum confirmation
    "bb": 0.15,         # Volatility
    "super_trend": 0.10,# Directional
    "adx": 0.05         # Trend strength
}
```

Additional v5 features:
- **ATR (Average True Range)**: Measures volatility for dynamic position sizing
- **Correlation filter**: Prevents holding both ETH and BTC (high correlation) if both trigger
- **Market regime detection**: Identifies BULL/BEAR/RANGING markets and adjusts weights

---

## Risk Management

### Position Sizing

Fixed percentage approach:
```python
position_size = capital × (POSITION_SIZE_PCT / 100)
# £500 capital × 15% = £75 per position
```

v5 uses ATR-adjusted sizing:
```python
# Larger positions in low volatility
# Smaller positions in high volatility
atr_adjusted_size = base_size × (reference_atr / current_atr)
```

### Exit Rules

```python
pnl_pct = (current_price - entry_price) / entry_price × 100

if pnl_pct >= TAKE_PROFIT_PCT:  # +3.0%
    SELL  # Take profit
elif pnl_pct <= -STOP_LOSS_PCT:  # -1.5%
    SELL  # Stop loss
elif signal == "SELL":
    SELL  # Strategy reversal
```

The tight stop loss (-1.5%) prevents large drawdowns. The 2:1 profit/loss
ratio (+3% / -1.5%) means you only need a 33% win rate to break even.

### Circuit Breakers

```python
# Daily loss limit
if daily_loss > DAILY_LOSS_LIMIT:
    halt_trading_until_next_day()

# Consecutive failures
if consecutive_fails >= 5:
    pause_for_cooldown()

# Exchange disconnect
if no_api_response_for(30_seconds):
    emergency_close_positions()
```

---

## Code Organization

### simple_multi_bot.py

The core bot (~450 lines) organized as:

| Class/Function | Purpose |
|---------------|---------|
| `KuCoinClient` | Async API wrapper with auth |
| `calculate_rsi()` | RSI indicator |
| `calculate_ema()` | EMA indicator |
| `calculate_atr()` | ATR volatility measure |
| `analyze_pair()` | Signal generation pipeline |
| `run_bot()` | Main event loop |

### multi_pair_portfolio_trader_v5.py

Advanced bot (~1250 lines) adds:

| Component | Purpose |
|-----------|---------|
| `ThinkingEmitter` | Visualization event stream |
| `PortfolioState` | Dataclass for portfolio tracking |
| `calculate_bollinger_bands()` | Volatility channel |
| `calculate_super_trend()` | Directional indicator |
| `calculate_adx()` | Trend strength |
| `ensemble_signal()` | Weighted multi-indicator score |
| `manage_portfolio()` | Correlation and sizing logic |
| `rebalance_positions()` | Weight re-calibration |

### multi_bot_monitor.py

Separate process that:
1. Parses bot logs via regex
2. Tracks closed trades
3. Sends Telegram notifications on:
   - Trade closures
   - Milestone achievements
   - Anomaly detection

This decouples monitoring from trading — the bot focuses on execution while
the monitor handles alerts.

---

## Performance Characteristics

### Latency
- KuCoin API round-trip: ~150ms
- 12 pairs × 150ms = 1.8s (sequential) vs ~200ms (concurrent with asyncio)
- Total cycle time: ~30 seconds (includes analysis + sleep)

### Throughput
- One trade decision per pair per 30s cycle
- Max 5 concurrent positions
- Estimated max: 100-200 trades/day depending on volatility

### Resource Usage
- CPU: Minimal (< 1% on modern hardware)
- Memory: ~50MB for Python process
- Network: ~50KB/minute (12 pairs × price + klines)

---

## Future Improvements

1. **Machine Learning**: Train classifier on historical signals vs outcomes
2. **On-chain Data**: Incorporate exchange flows, whale movements
3. **Options Hedging**: Buy puts when portfolio delta exceeds threshold
4. **Multi-Exchange**: Arbitrage opportunities across exchanges
5. **Backtesting Framework**: Validate strategies on historical data

---

## References

- [KuCoin API Docs](https://docs.kucoin.com/)
- RSI: Welles Wilder, "New Concepts in Technical Trading Systems" (1978)
- EMA: Patrick Mulloy, "Smoothing Data with Faster Moving Averages" (1994)
- ATR: Welles Wilder, "New Concepts in Technical Trading Systems" (1978)
