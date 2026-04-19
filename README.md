# Multi-Pair Crypto Trading Bot

A lightweight, production-ready multi-pair cryptocurrency trading bot for KuCoin.
This bot monitors multiple trading pairs simultaneously and makes automated
trading decisions based on technical analysis.

> **⚠️ Risk Warning**: This software is for educational and research purposes.
> Cryptocurrency trading carries significant risk. Always start with dry-run mode.

---

## Quick Start

```bash
# 1. Clone and enter directory
cd multi-pair-crypto-trader

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment template and fill in your credentials
cp .env.example .env
# Edit .env with your KuCoin API keys (only needed for live trading)

# 4. Run in simulation mode (no real trades)
python3 run_multi_pair_bot.py --dry-run

# 5. Generate performance report
python3 run_multi_pair_bot.py --report
```

---

## What's Included

| File | Description |
|------|-------------|
| `simple_multi_bot.py` | **Core bot** - multi-pair trader with RSI/EMA signals |
| `multi_pair_portfolio_trader_v5.py` | **Advanced v5 bot** - ensemble signals, correlation analysis, portfolio rebalancing |
| `multi_pair_bot_supertrend_v6.py` | **SuperTrend Alpha v6** - tightened single-signal strategy, 1% risk sizing |
| `multi_bot_monitor.py` | **Trade monitor** - tracks closures and sends notifications |
| `multi_bot_report.py` | **Report generator** - prints comprehensive performance stats |
| `run_multi_pair_bot.py` | **Launcher** - convenient CLI for running all components |
| `.env.example` | **Credential template** - copy to `.env` and fill in |

---

## How It Works

### Multi-Pair Strategy

Traditional bots trade only one pair (e.g., ETH-USDT). If that pair enters a
"chop zone" — moving sideways with no clear trend — the bot either loses money
on false signals or sits idle for long periods.

**This bot solves that by monitoring 12 pairs at once:**

- ETH-USDT, BTC-USDT, SOL-USDT, LINK-USDT
- AVAX-USDT, DOT-USDT, MATIC-USDT, UNI-USDT
- AAVE-USDT, ATOM-USDT, ADA-USDT, DOGE-USDT

By diversifying across multiple assets, the bot captures opportunities wherever
they arise, rather than being hostage to a single asset's boredom.

### Signal Engine (v4.1)

Each pair is analyzed every cycle using:

1. **RSI(14)** — Identifies oversold conditions (< 30 = potential buy)
2. **EMA(9/21)** — Confirms short-term uptrend (fast > slow)
3. **MACD** — Momentum confirmation
4. **Volume** — Above-average volume validates the move

A composite score is calculated. Only pairs scoring ≥ 0.7 trigger a `BUY` signal.

### Risk Controls

- **Position Sizing**: 15% of capital per trade (max 5 positions)
- **Take Profit**: +3.0%
- **Stop Loss**: -1.5%
- **Max Positions**: 5 concurrent trades
- **Dry-Run Mode**: Paper trade with zero risk

---

## SuperTrend Alpha Bot (v6)

The `multi_pair_bot_supertrend_v6.py` is a **complete strategy overhaul** built after analyzing 835+ cycles of zero trades on the v5 ensemble approach. The problem: too many indicators requiring alignment created an impossibly tight filter. v6 solves this with a **single dominant signal + strict confirmation filters**.

### What Changed from v5

| Aspect | v5 (Old) | v6 (New) |
|--------|----------|----------|
| **Signal Engine** | 7-indicator ensemble (RSI, EMA, MACD, BB, ATR, SuperTrend, ADX) requiring composite alignment | Single SuperTrend(10, 2.0) as primary signal |
| **Entry Filters** | Loose — any 4 of 7 indicators could align | Strict — ALL 3 filters must pass (ADX>20, Price>EMA20, Volume>SMA20×0.8) |
| **Position Sizing** | Fixed % of capital per trade | **1% account risk per trade** with ATR-based sizing (~$0.70 risk on $70) |
| **Pairs** | 12 pairs (including mid-caps) | 4 pairs: BTC, ETH, SOL, BNB |
| **Max Positions** | 5 | **3** |
| **Stop Loss** | Static -1.5% | Dynamic ATR-based (2.5× ATR) |
| **Take Profit** | Static +3.0% | SuperTrend flip + trailing stop (+2% activates trail) |
| **Drawdown Protection** | None | **8% portfolio drawdown = emergency halt** |
| **Daily Loss Limit** | None | **3% daily loss = stop trading** |
| **Cooldown** | None | **3 losses in 1 hour = 30min cooldown** |

### v6 Signal Logic

```
SUPERTREND DIRECTION = BULLISH
    AND ADX > 20              (trending market, not chop)
    AND Price > EMA20         (trend alignment)
    AND Volume > SMA20 × 0.8  (confirmation)
    AND Active Positions < 3  (capacity)
    AND Account > $5.01       (minimum order)
    AND Drawdown < 8%         (safety)
→ ENTER LONG

EXIT when:
    SuperTrend flips BEARISH  (primary exit)
    OR Price hits ATR Stop    (2.5× ATR below entry)
    OR Trailing stop hit      (after +2% profit, trail at 1.5× ATR)
```

### Why This Works Better for Small Accounts

- **Fewer, higher-quality trades**: v5 demanded perfection from 7 indicators — rarely happened. v6 demands one clear signal with 3 confirmations — happens more often but only in genuine trends.
- **Risk-defined sizing**: 1% risk means you can survive 30 consecutive losses before hitting 30% drawdown. With $70, each trade risks ~$0.70.
- **Concentrated watchlist**: 4 liquid pairs instead of 12 — less noise, faster execution, tighter spreads.
- **Triple safety net**: Drawdown halt + daily loss limit + loss-cluster cooldown prevents death spirals.

Run with:
```bash
python3 multi_pair_bot_supertrend_v6.py --capital 70 --max-pairs 3
```

---

## Advanced Bot (v5)

The `multi_pair_portfolio_trader_v5.py` includes:

- **7-indicator ensemble**: RSI, EMA, MACD, Bollinger Bands, ATR, SuperTrend, ADX
- **Pair correlation filter**: Prevents over-concentration in correlated assets
- **Dynamic position sizing**: Adjusts based on volatility (ATR)
- **Portfolio rebalancing**: Re-calibrates weights every 100 trades
- **Thinking stream**: Emits visualization events for dashboards

Run with:
```bash
python3 run_multi_pair_bot.py --v5 --dry-run
```

---

## Configuration

Edit `.env` to customize:

```env
# KuCoin API credentials (required for live mode)
KUCOIN_API_KEY=your_key_here
KUCOIN_API_SECRET=your_secret_here
KUCOIN_PASSPHRASE=your_passphrase_here

# Portfolio settings
PORTFOLIO_CAPITAL=500
MAX_PAIRS=5
MAX_POSITION_PCT=15

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## Command Reference

```bash
# Run simple bot in dry-run mode
python3 run_multi_pair_bot.py --dry-run

# Run simple bot in live mode with $500
python3 run_multi_pair_bot.py --live --capital 500

# Run advanced v5 bot in dry-run mode
python3 run_multi_pair_bot.py --v5 --dry-run

# Run SuperTrend Alpha v6 (live trading)
python3 multi_pair_bot_supertrend_v6.py --capital 70 --max-pairs 3

# Run SuperTrend Alpha v6 (dry-run / paper trading)
python3 multi_pair_bot_supertrend_v6.py --dry-run --capital 1000 --max-pairs 3

# Run monitor (checks logs and sends notifications)
python3 run_multi_pair_bot.py --monitor

# Generate performance report
python3 run_multi_pair_bot.py --report

# Direct bot execution
python3 simple_multi_bot.py --dry-run --capital 1000 --max-positions 3 --position-size 20
```

---

## Project Philosophy

This repository documents the **evolution from single-pair to multi-pair trading**:

| Version | Pairs | Key Innovation | Status |
|---------|-------|---------------|--------|
| v1 | 1 | Basic market orders | Archived |
| v2 | 1 | TP/SL with logging | Archived |
| v3 | 1 | Telegram + dashboard | Archived |
| v4 | 1 | RSI/EMA + TradingGuard | Active (single pair) |
| v4.1 | 12 | Multi-pair expansion | **Core bot** |
| v5 | 12 | Ensemble signals + portfolio mgmt | **Advanced** |
| v6 | 4 | SuperTrend Alpha + 1% risk sizing + triple safety | **Latest / Live** |

The progression shows how boredom/chop in a single asset led to diversification
as the primary strategy improvement.

---

## Architecture

For a deep dive into the code architecture, signal algorithms, and design
decisions, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## License

MIT License — use at your own risk. This is not financial advice.
