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

The progression shows how boredom/chop in a single asset led to diversification
as the primary strategy improvement.

---

## Architecture

For a deep dive into the code architecture, signal algorithms, and design
decisions, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## License

MIT License — use at your own risk. This is not financial advice.
