#!/usr/bin/env python3
"""
V6 SuperTrend Alpha Backtester - Fixed Portfolio Simulation
"""

import asyncio
import aiohttp
import json
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import copy

# ─── Configuration ────────────────────────────────────────────────

PAIRS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT"]
TIMEFRAME = "1hour"
DAYS_OF_DATA = 120
INITIAL_CAPITAL = 1000
RISK_PER_TRADE = 0.01
COMMISSION = 0.001
MAX_POSITIONS = 3

THRESHOLD_TESTS = [
    {"name": "v6_current", "adx": 20, "ema": True, "vol": 0.8, "min_strength": 0.0, "desc": "Current v6 (too strict)"},
    {"name": "v6_loose_adx", "adx": 15, "ema": True, "vol": 0.8, "min_strength": 0.0, "desc": "Lower ADX only"},
    {"name": "v6_no_ema", "adx": 20, "ema": False, "vol": 0.8, "min_strength": 0.0, "desc": "No EMA filter"},
    {"name": "v6_balanced", "adx": 15, "ema": True, "vol": 0.5, "min_strength": 0.0, "desc": "Relaxed filters"},
    {"name": "v6_strength", "adx": 15, "ema": False, "vol": 0.0, "min_strength": 0.50, "desc": "Strength-based entry"},
    {"name": "v5_style", "adx": 15, "ema": True, "vol": 0.5, "min_strength": 0.45, "desc": "V5-like threshold"},
    {"name": "v6_aggressive", "adx": 12, "ema": False, "vol": 0.0, "min_strength": 0.40, "desc": "Aggressive entries"},
    {"name": "v6_conservative", "adx": 18, "ema": True, "vol": 0.6, "min_strength": 0.55, "desc": "Conservative but tradable"},
]

# ─── Data & Indicators ────────────────────────────────────────────

async def fetch_klines(session, symbol, timeframe, start_at, end_at):
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {"type": timeframe, "symbol": symbol, "startAt": start_at, "endAt": end_at}
    try:
        async with session.get(url, params=params, timeout=30) as resp:
            data = await resp.json()
            if data.get("data"):
                candles = []
                for c in data["data"]:
                    candles.append({"timestamp": int(c[0]), "open": float(c[1]), "close": float(c[2]),
                                    "high": float(c[3]), "low": float(c[4]), "volume": float(c[5])})
                return sorted(candles, key=lambda x: x["timestamp"])
    except Exception as e:
        print(f"Error: {e}")
    return []

def ema(prices, period):
    if len(prices) < period:
        return prices
    mult = 2 / (period + 1)
    result = [float(np.mean(prices[:period]))]
    for p in prices[period:]:
        result.append(p * mult + result[-1] * (1 - mult))
    return result

def atr(highs, lows, closes, period=10):
    if len(closes) < period + 1:
        return [0.0] * len(closes)
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    atr_vals = [np.mean(tr_list[:i+1]) if i < period else np.mean(tr_list[i-period+1:i+1]) for i in range(len(tr_list))]
    atr_vals = [atr_vals[0]] + atr_vals
    return atr_vals

def supertrend(highs, lows, closes, period=10, multiplier=2.0):
    atr_vals = atr(highs, lows, closes, period)
    directions, st_lines = [], []
    upper_band, lower_band = [], []
    
    for i in range(len(closes)):
        if i < period:
            directions.append("NEUTRAL")
            st_lines.append(closes[i])
            upper_band.append(highs[i] + multiplier * atr_vals[i])
            lower_band.append(lows[i] - multiplier * atr_vals[i])
            continue
        
        basic_upper = (highs[i] + lows[i]) / 2 + multiplier * atr_vals[i]
        basic_lower = (highs[i] + lows[i]) / 2 - multiplier * atr_vals[i]
        
        prev_upper = upper_band[-1]
        prev_lower = lower_band[-1]
        
        curr_upper = basic_upper if basic_upper < prev_upper or closes[i-1] > prev_upper else prev_upper
        curr_lower = basic_lower if basic_lower > prev_lower or closes[i-1] < prev_lower else prev_lower
        
        upper_band.append(curr_upper)
        lower_band.append(curr_lower)
        
        if closes[i] > curr_upper:
            directions.append("BULLISH")
            st_lines.append(curr_lower)
        elif closes[i] < curr_lower:
            directions.append("BEARISH")
            st_lines.append(curr_upper)
        else:
            directions.append(directions[-1] if directions else "NEUTRAL")
            st_lines.append(curr_lower if directions[-1] == "BULLISH" else curr_upper)
    
    return directions, st_lines

def adx_indicator(highs, lows, closes, period=14):
    if len(closes) < period * 2:
        return [20.0] * len(closes)
    
    tr_list = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
    plus_dm = [max(highs[i] - highs[i-1], 0) if highs[i] - highs[i-1] > lows[i-1] - lows[i] else 0 for i in range(1, len(closes))]
    minus_dm = [max(lows[i-1] - lows[i], 0) if lows[i-1] - lows[i] > highs[i] - highs[i-1] else 0 for i in range(1, len(closes))]
    
    atr_smoothed = [np.mean(tr_list[:period])]
    plus_dm_smoothed = [np.mean(plus_dm[:period])]
    minus_dm_smoothed = [np.mean(minus_dm[:period])]
    
    for i in range(period, len(tr_list)):
        atr_smoothed.append(atr_smoothed[-1] - atr_smoothed[-1]/period + tr_list[i])
        plus_dm_smoothed.append(plus_dm_smoothed[-1] - plus_dm_smoothed[-1]/period + plus_dm[i])
        minus_dm_smoothed.append(minus_dm_smoothed[-1] - minus_dm_smoothed[-1]/period + minus_dm[i])
    
    adx_vals = [20.0] * (period + 1)
    for i in range(period, len(atr_smoothed)):
        if atr_smoothed[i] > 0:
            plus_di = 100 * plus_dm_smoothed[i] / atr_smoothed[i]
            minus_di = 100 * minus_dm_smoothed[i] / atr_smoothed[i]
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            adx_vals.append(dx)
        else:
            adx_vals.append(0)
    
    # Smooth DX
    adx_smoothed = adx_vals[:period*2]
    for i in range(period*2, len(adx_vals)):
        adx_smoothed.append(adx_smoothed[-1] - adx_smoothed[-1]/period + adx_vals[i])
    
    while len(adx_smoothed) < len(closes):
        adx_smoothed.insert(0, 20.0)
    return adx_smoothed[:len(closes)]

# ─── Proper Portfolio Backtest ────────────────────────────────────

@dataclass
class Trade:
    pair: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime = None
    exit_price: float = 0
    size_usdt: float = 0
    pnl_usdt: float = 0
    pnl_pct: float = 0
    reason: str = ""

class PortfolioBacktest:
    def __init__(self, all_candles: Dict[str, List[dict]], config: dict):
        self.all_candles = all_candles
        self.config = config
        self.balance = INITIAL_CAPITAL
        self.peak_balance = INITIAL_CAPITAL
        self.max_drawdown = 0
        self.trades = []
        self.equity_curve = []
        
    def run(self):
        # Precompute signals for all pairs
        pair_signals = {}
        all_events = []  # (timestamp, pair, type, data)
        
        for pair, candles in self.all_candles.items():
            if len(candles) < 100:
                continue
                
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            closes = [c["close"] for c in candles]
            volumes = [c["volume"] for c in candles]
            timestamps = [datetime.fromtimestamp(c["timestamp"]) for c in candles]
            
            st_dirs, st_lines = supertrend(highs, lows, closes, 10, 2.0)
            ema20_vals = ema(closes, 20)
            # Pad EMA to match closes length
            while len(ema20_vals) < len(closes):
                ema20_vals.insert(0, closes[0])
            adx_vals = adx_indicator(highs, lows, closes, 14)
            
            signals = []
            start_idx = 50
            
            for i in range(start_idx, len(closes)):
                close = closes[i]
                vol_sma = np.mean(volumes[max(0, i-20):i+1])
                cfg = self.config
                
                adx_ok = adx_vals[i] >= cfg["adx"]
                above_ema = close > ema20_vals[i] if cfg["ema"] else True
                vol_ok = volumes[i] >= vol_sma * cfg["vol"] if cfg["vol"] > 0 else True
                
                adx_score = min(1.0, adx_vals[i] / 40.0)
                ema_score = min(1.0, (close / ema20_vals[i] - 1) * 50 + 0.5) if ema20_vals[i] > 0 else 0.5
                
                if st_dirs[i] == "BULLISH":
                    st_score = min(1.0, (close - st_lines[i]) / (close * 0.01) + 0.5) if st_lines[i] > 0 else 1.0
                    strength = st_score * 0.5 + adx_score * 0.25 + (1.0 if above_ema else 0.0) * 0.15 + (1.0 if vol_ok else 0.0) * 0.10
                    
                    if adx_ok and above_ema and vol_ok and strength >= cfg.get("min_strength", 0):
                        signals.append({
                            "time": timestamps[i],
                            "type": "ENTRY",
                            "price": close,
                            "pair": pair,
                            "atr": atr([highs[i]], [lows[i]], [close], 10)[0],
                            "st_line": st_lines[i],
                        })
                
                # Check for exit signal
                if st_dirs[i] == "BEARISH":
                    signals.append({
                        "time": timestamps[i],
                        "type": "EXIT_SIGNAL",
                        "price": close,
                        "pair": pair,
                        "reason": "SUPERTREND_FLIP",
                    })
                
                signals.append({
                    "time": timestamps[i],
                    "type": "BAR",
                    "price": close,
                    "pair": pair,
                    "high": highs[i],
                    "low": lows[i],
                })
            
            pair_signals[pair] = signals
            all_events.extend(signals)
        
        # Sort all events by time
        all_events.sort(key=lambda x: x["time"])
        
        # Simulate
        positions = {}  # pair -> position dict
        
        for event in all_events:
            pair = event["pair"]
            
            # Update equity tracking
            current_equity = self.balance + sum(
                pos["size_usdt"] * (event["price"] - pos["entry_price"]) / pos["entry_price"]
                for p, pos in positions.items()
            )
            self.equity_curve.append(current_equity)
            
            if current_equity > self.peak_balance:
                self.peak_balance = current_equity
            dd = (self.peak_balance - current_equity) / self.peak_balance
            if dd > self.max_drawdown:
                self.max_drawdown = dd
            
            if event["type"] == "ENTRY":
                if len(positions) >= MAX_POSITIONS:
                    continue
                if pair in positions:
                    continue
                
                risk_amount = self.balance * RISK_PER_TRADE
                stop_distance = event["atr"] * 2.5 if event["atr"] > 0 else event["price"] * 0.02
                
                if stop_distance > 0:
                    position_size = risk_amount / (stop_distance / event["price"])
                    position_size = min(position_size, self.balance * 0.15)
                    position_size = max(position_size, 5)
                    position_size = min(position_size, self.balance * 0.95)
                    
                    positions[pair] = {
                        "entry_price": event["price"],
                        "size_usdt": position_size,
                        "stop_loss": event["price"] - stop_distance,
                        "highest_price": event["price"],
                        "entry_time": event["time"],
                    }
            
            elif event["type"] == "BAR" and pair in positions:
                pos = positions[pair]
                if event["high"] > pos["highest_price"]:
                    pos["highest_price"] = event["high"]
                
                # Check stops
                exit_price = None
                reason = None
                
                if event["low"] <= pos["stop_loss"]:
                    exit_price = pos["stop_loss"]
                    reason = "STOP_LOSS"
                elif event["price"] >= pos["entry_price"] * 1.02:
                    trail_stop = pos["highest_price"] - (pos["highest_price"] - pos["entry_price"]) * 0.5
                    if event["low"] <= trail_stop:
                        exit_price = trail_stop
                        reason = "TRAILING_STOP"
                
                if exit_price:
                    pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
                    pnl_usdt = pos["size_usdt"] * pnl_pct - pos["size_usdt"] * COMMISSION * 2
                    self.balance += pnl_usdt
                    
                    self.trades.append(Trade(
                        pair=pair, entry_time=pos["entry_time"], entry_price=pos["entry_price"],
                        exit_time=event["time"], exit_price=exit_price,
                        size_usdt=pos["size_usdt"], pnl_usdt=pnl_usdt, pnl_pct=pnl_pct*100, reason=reason
                    ))
                    del positions[pair]
            
            elif event["type"] == "EXIT_SIGNAL" and pair in positions:
                pos = positions[pair]
                pnl_pct = (event["price"] - pos["entry_price"]) / pos["entry_price"]
                pnl_usdt = pos["size_usdt"] * pnl_pct - pos["size_usdt"] * COMMISSION * 2
                self.balance += pnl_usdt
                
                self.trades.append(Trade(
                    pair=pair, entry_time=pos["entry_time"], entry_price=pos["entry_price"],
                    exit_time=event["time"], exit_price=event["price"],
                    size_usdt=pos["size_usdt"], pnl_usdt=pnl_usdt, pnl_pct=pnl_pct*100, reason="SUPERTREND_FLIP"
                ))
                del positions[pair]
        
        # Close remaining positions at last price
        for pair, pos in positions.items():
            # Find last price
            last_price = pos["entry_price"]  # fallback
            for ev in reversed(all_events):
                if ev["pair"] == pair and ev["type"] == "BAR":
                    last_price = ev["price"]
                    break
            
            pnl_pct = (last_price - pos["entry_price"]) / pos["entry_price"]
            pnl_usdt = pos["size_usdt"] * pnl_pct - pos["size_usdt"] * COMMISSION * 2
            self.balance += pnl_usdt
            
            self.trades.append(Trade(
                pair=pair, entry_time=pos["entry_time"], entry_price=pos["entry_price"],
                exit_time=all_events[-1]["time"] if all_events else pos["entry_time"], exit_price=last_price,
                size_usdt=pos["size_usdt"], pnl_usdt=pnl_usdt, pnl_pct=pnl_pct*100, reason="END_OF_DATA"
            ))
        
        return self._build_result()
    
    def _build_result(self):
        winning = [t for t in self.trades if t.pnl_usdt > 0]
        losing = [t for t in self.trades if t.pnl_usdt <= 0]
        gross_profit = sum(t.pnl_usdt for t in winning) if winning else 0
        gross_loss = abs(sum(t.pnl_usdt for t in losing)) if losing else 1e-9
        
        returns = []
        for i in range(1, len(self.equity_curve)):
            if self.equity_curve[i-1] > 0:
                returns.append((self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1])
        
        sharpe = 0
        if returns and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(365 * 24)
        
        return {
            "name": self.config["name"],
            "desc": self.config["desc"],
            "trades": len(self.trades),
            "wins": len(winning),
            "losses": len(losing),
            "win_rate": len(winning) / len(self.trades) * 100 if self.trades else 0,
            "return_pct": (self.balance - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
            "max_dd_pct": self.max_drawdown * 100,
            "sharpe": sharpe,
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else 0,
            "avg_trade": sum(t.pnl_usdt for t in self.trades) / len(self.trades) if self.trades else 0,
            "final_balance": self.balance,
            "trade_list": self.trades,
        }

# ─── Main ─────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("SUPERTREND ALPHA V6 - PORTFOLIO BACKTEST (Fixed)")
    print("=" * 80)
    print(f"Pairs: {', '.join(PAIRS)}")
    print(f"Capital: ${INITIAL_CAPITAL} | Risk: {RISK_PER_TRADE*100}% | Max Positions: {MAX_POSITIONS}")
    print()
    
    end_time = int(datetime.now().timestamp())
    start_time = int((datetime.now() - timedelta(days=DAYS_OF_DATA)).timestamp())
    
    async with aiohttp.ClientSession() as session:
        all_candles = {}
        for pair in PAIRS:
            print(f"📊 Fetching {pair}...", end=" ")
            candles = await fetch_klines(session, pair, TIMEFRAME, start_time, end_time)
            if len(candles) >= 100:
                all_candles[pair] = candles
                print(f"✓ {len(candles)} candles ({len(candles)/24:.0f} days)")
            else:
                print(f"✗ Only {len(candles)} candles")
        
        print()
        print("=" * 80)
        print("RUNNING PORTFOLIO SIMULATIONS")
        print("=" * 80)
        
        results = []
        for cfg in THRESHOLD_TESTS:
            engine = PortfolioBacktest(all_candles, cfg)
            result = engine.run()
            results.append(result)
        
        # Sort by return
        results.sort(key=lambda x: x["return_pct"], reverse=True)
        
        print(f"\n{'Rank':>4} {'Config':<20} {'Trades':>6} {'Win%':>7} {'Return':>9} {'MaxDD':>8} {'Sharpe':>7} {'PF':>6} {'AvgTrade':>9} {'Final $':>10}")
        print("-" * 95)
        
        for i, r in enumerate(results, 1):
            print(f"{i:>4} {r['name']:<20} {r['trades']:>6} {r['win_rate']:>6.1f}% {r['return_pct']:>8.2f}% {r['max_dd_pct']:>7.2f}% {r['sharpe']:>6.2f} {r['profit_factor']:>5.2f} ${r['avg_trade']:>8.2f} ${r['final_balance']:>8.2f}")
        
        # Detailed analysis of top 3
        print("\n" + "=" * 80)
        print("TOP 3 CONFIGURATIONS - DETAILED ANALYSIS")
        print("=" * 80)
        
        for i, r in enumerate(results[:3], 1):
            print(f"\n{'─' * 80}")
            print(f"#{i} {r['name']} - {r['desc']}")
            print(f"{'─' * 80}")
            print(f"  Total Trades: {r['trades']} ({r['wins']} wins, {r['losses']} losses)")
            print(f"  Win Rate: {r['win_rate']:.1f}%")
            print(f"  Total Return: {r['return_pct']:.2f}%")
            print(f"  Max Drawdown: {r['max_dd_pct']:.2f}%")
            print(f"  Sharpe Ratio: {r['sharpe']:.2f}")
            print(f"  Profit Factor: {r['profit_factor']:.2f}")
            print(f"  Average Trade: ${r['avg_trade']:.2f}")
            
            # Breakdown by pair
            pair_stats = {}
            for t in r['trade_list']:
                if t.pair not in pair_stats:
                    pair_stats[t.pair] = {"trades": 0, "pnl": 0, "wins": 0}
                pair_stats[t.pair]["trades"] += 1
                pair_stats[t.pair]["pnl"] += t.pnl_usdt
                if t.pnl_usdt > 0:
                    pair_stats[t.pair]["wins"] += 1
            
            print(f"\n  By Pair:")
            for pair, stats in sorted(pair_stats.items()):
                wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
                print(f"    {pair}: {stats['trades']} trades, ${stats['pnl']:.2f} PnL, {wr:.0f}% WR")
            
            # Monthly breakdown
            monthly = {}
            for t in r['trade_list']:
                month = t.entry_time.strftime("%Y-%m")
                if month not in monthly:
                    monthly[month] = 0
                monthly[month] += t.pnl_usdt
            
            print(f"\n  Monthly PnL:")
            for month, pnl in sorted(monthly.items()):
                bar = "█" * int(abs(pnl) / 2)
                print(f"    {month}: ${pnl:>7.2f} {bar}")
            
            # Annual projection
            months = DAYS_OF_DATA / 30
            monthly_return = r['return_pct'] / months
            annual_projected = monthly_return * 12
            
            # Compounded
            monthly_mult = 1 + r['return_pct'] / 100 / months
            annual_compound = (monthly_mult ** 12 - 1) * 100
            
            print(f"\n  📊 Projections (if performance continues):")
            print(f"     Monthly avg return: {monthly_return:.2f}%")
            print(f"     Simple annual: {annual_projected:.0f}%")
            print(f"     Compounded annual: {annual_compound:.0f}%")
            print(f"     $1,000 → ${1000 * (1 + annual_compound/100):.0f} by year-end")
        
        # Print recommended config
        best = results[0]
        print("\n" + "=" * 80)
        print("RECOMMENDED CONFIGURATION")
        print("=" * 80)
        
        for cfg in THRESHOLD_TESTS:
            if cfg["name"] == best["name"]:
                print(f"\n✅ Use: {cfg['name']}")
                print(f"   ADX Threshold: {cfg['adx']}")
                print(f"   EMA Filter: {'ON' if cfg['ema'] else 'OFF'}")
                print(f"   Volume Filter: {cfg['vol']*100:.0f}% of SMA")
                print(f"   Min Strength: {cfg.get('min_strength', 0)}")
                
                print(f"\n💡 To apply this to your bot, modify these lines in v6:")
                print(f"   ADX_THRESHOLD = {cfg['adx']}")
                if not cfg['ema']:
                    print(f"   # Comment out or remove the EMA check in _determine_signal()")
                if cfg['vol'] == 0:
                    print(f"   # Comment out or remove the volume check in _determine_signal()")
                if cfg.get('min_strength', 0) > 0:
                    print(f"   Add: if strength < {cfg['min_strength']}: return 'HOLD', strength")
                break

if __name__ == "__main__":
    asyncio.run(main())
