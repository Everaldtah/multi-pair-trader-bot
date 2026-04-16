#!/usr/bin/env python3
"""
Simple Multi-Pair Trading Bot - Dry Run Mode
============================================
Monitors multiple pairs and simulates trades.
"""

import os
import sys
import time
import json
import hmac
import hashlib
import base64
import asyncio
import aiohttp
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
from collections import deque

# Load env
env_path = "/root/.env"
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            os.environ[key.strip()] = val.strip().strip('\'"')

KUCOIN_API_KEY = os.environ.get("KUCOIN_API_KEY", "")
KUCOIN_API_SECRET = os.environ.get("KUCOIN_API_SECRET", "")
KUCOIN_PASSPHRASE = os.environ.get("KUCOIN_PASSPHRASE", "")

# Config
SIMULATED_CAPITAL = 500  # £500
MAX_POSITIONS = 5
POSITION_SIZE_PCT = 15  # 15% per position

trade_log = []

class KuCoinClient:
    BASE_URL = "https://api.kucoin.com"
    
    def __init__(self):
        self.session = None
        
    async def connect(self):
        self.session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json", "KC-API-KEY-VERSION": "2"},
            timeout=aiohttp.ClientTimeout(total=30)
        )
        
    async def close(self):
        if self.session:
            await self.session.close()
            
    def _sign(self, method: str, endpoint: str):
        now = int(time.time() * 1000)
        str_to_sign = f"{now}{method.upper()}{endpoint}"
        signature = base64.b64encode(
            hmac.new(KUCOIN_API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()
        ).decode()
        passphrase_sig = base64.b64encode(
            hmac.new(KUCOIN_API_SECRET.encode(), KUCOIN_PASSPHRASE.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "KC-API-KEY": KUCOIN_API_KEY,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": str(now),
            "KC-API-PASSPHRASE": passphrase_sig,
        }
    
    async def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get current prices for multiple symbols."""
        prices = {}
        for symbol in symbols:
            try:
                headers = self._sign("GET", f"/api/v1/market/orderbook/level1?symbol={symbol}")
                url = f"{self.BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol}"
                async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    if data.get("code") == "200000":
                        prices[symbol] = float(data["data"].get("price", 0))
            except Exception as e:
                print(f"  ⚠️  Error getting {symbol}: {e}")
        return prices
    
    async def get_klines(self, symbol: str, interval: str = "1hour", limit: int = 50) -> List[List]:
        """Get candle data."""
        try:
            headers = self._sign("GET", "/api/v1/market/candles")
            params = {"symbol": symbol, "type": interval}
            url = f"{self.BASE_URL}/api/v1/market/candles"
            async with self.session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("code") == "200000" and data.get("data"):
                    return list(reversed(data["data"][-limit:]))
        except Exception as e:
            print(f"  ⚠️  Error getting klines for {symbol}: {e}")
        return []

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI indicator."""
    if len(prices) < period + 1:
        return 50.0
    
    deltas = np.diff(prices)
    gains = deltas[deltas > 0]
    losses = -deltas[deltas < 0]
    
    avg_gain = np.mean(gains) if len(gains) > 0 else 0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(prices: List[float], period: int) -> float:
    """Calculate EMA."""
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = np.mean(prices[:period])
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """Calculate Average True Range."""
    if len(closes) < period + 1:
        return 0
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    return np.mean(tr_list[-period:]) if tr_list else 0

async def analyze_pair(client: KuCoinClient, symbol: str) -> Dict:
    """Analyze a trading pair and return signals."""
    klines = await client.get_klines(symbol, "1hour", 50)
    if not klines or len(klines) < 30:
        return {"symbol": symbol, "signal": "HOLD", "score": 0.5}
    
    # Parse klines
    closes = [float(k[2]) for k in klines]
    highs = [float(k[3]) for k in klines]
    lows = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    
    current_price = closes[-1]
    
    # Calculate indicators
    rsi = calculate_rsi(closes, 14)
    ema_fast = calculate_ema(closes, 9)
    ema_slow = calculate_ema(closes, 21)
    atr = calculate_atr(highs, lows, closes, 14)
    
    # Volume trend
    volume_avg = np.mean(volumes[-10:])
    volume_now = volumes[-1]
    volume_ratio = volume_now / volume_avg if volume_avg > 0 else 1
    
    # Signal scoring
    score = 0.5  # Neutral
    
    # RSI component (oversold = buy signal)
    if rsi < 30:
        score += 0.2
    elif rsi > 70:
        score -= 0.2
    
    # EMA trend component
    if ema_fast > ema_slow:
        score += 0.15
    else:
        score -= 0.15
    
    # Volume confirmation
    if volume_ratio > 1.5:
        score += 0.1
    
    # Determine signal
    if score >= 0.7:
        signal = "BUY"
    elif score <= 0.3:
        signal = "SELL"
    else:
        signal = "HOLD"
    
    return {
        "symbol": symbol,
        "price": current_price,
        "rsi": rsi,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "atr": atr,
        "volume_ratio": volume_ratio,
        "score": score,
        "signal": signal
    }

async def run_bot():
    """Main bot loop."""
    
    # Watchlist - top crypto pairs
    watchlist = [
        "ETH-USDT", "BTC-USDT", "SOL-USDT", "LINK-USDT",
        "AVAX-USDT", "DOT-USDT", "MATIC-USDT", "UNI-USDT",
        "AAVE-USDT", "ATOM-USDT", "ADA-USDT", "DOGE-USDT"
    ]
    
    print("=" * 70)
    print("🚀 MULTI-PAIR PORTFOLIO TRADER - DRY RUN MODE")
    print("=" * 70)
    print(f"💰 Simulated Capital: £{SIMULATED_CAPITAL}")
    print(f"📊 Max Positions: {MAX_POSITIONS}")
    print(f"💵 Position Size: {POSITION_SIZE_PCT}% per trade")
    print(f"📈 Pairs Monitored: {len(watchlist)}")
    print("=" * 70)
    print()
    
    client = KuCoinClient()
    await client.connect()
    print("✅ Connected to KuCoin API")
    print()
    
    # Portfolio state
    positions = {}  # symbol -> {entry_price, size, pnl}
    available_capital = SIMULATED_CAPITAL
    total_pnl = 0
    cycle = 0
    
    try:
        while True:
            cycle += 1
            print(f"\n{'=' * 70}")
            print(f"🔄 CYCLE {cycle} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'=' * 70}")
            print(f"💼 Open Positions: {len(positions)}/{MAX_POSITIONS}")
            print(f"💵 Available: £{available_capital:.2f} | P&L: £{total_pnl:.2f}")
            print()
            
            # Analyze all pairs
            print("📊 Analyzing pairs...")
            analyses = []
            for symbol in watchlist:
                analysis = await analyze_pair(client, symbol)
                analyses.append(analysis)
                await asyncio.sleep(0.1)  # Rate limit
            
            # Sort by score (best opportunities first)
            analyses.sort(key=lambda x: x["score"], reverse=True)
            
            # Display analysis
            print("\n📈 Pair Analysis:")
            print(f"{'Symbol':<12} {'Price':<10} {'RSI':<6} {'Signal':<8} {'Score':<6}")
            print("-" * 50)
            for a in analyses[:8]:  # Show top 8
                if "price" not in a:
                    continue  # Skip pairs without price data
                emoji = "🟢" if a["signal"] == "BUY" else ("🔴" if a["signal"] == "SELL" else "⚪")
                print(f"{emoji} {a['symbol']:<10} ${a['price']:<9.2f} {a['rsi']:<5.1f} {a['signal']:<7} {a['score']:.2f}")
            
            # Check for buy signals
            print("\n💡 Trade Evaluation:")
            buy_candidates = [a for a in analyses if a.get("signal") == "BUY" and a.get("symbol") not in positions and "price" in a]
            
            if buy_candidates and len(positions) < MAX_POSITIONS:
                for candidate in buy_candidates[:MAX_POSITIONS - len(positions)]:
                    symbol = candidate["symbol"]
                    price = candidate["price"]
                    position_size = SIMULATED_CAPITAL * (POSITION_SIZE_PCT / 100)
                    
                    if available_capital >= position_size:
                        # Simulate buy
                        positions[symbol] = {
                            "entry_price": price,
                            "size": position_size,
                            "entry_time": datetime.now()
                        }
                        available_capital -= position_size
                        
                        trade = {
                            "time": datetime.now().isoformat(),
                            "action": "BUY",
                            "symbol": symbol,
                            "price": price,
                            "size": position_size
                        }
                        trade_log.append(trade)
                        
                        print(f"  🟢 BUY {symbol} @ ${price:.2f} | Size: £{position_size:.2f}")
            else:
                if len(positions) >= MAX_POSITIONS:
                    print("  ⏸️  Max positions reached")
                elif not buy_candidates:
                    print("  ⏸️  No buy signals")
            
            # Check for sell signals on open positions
            for symbol, pos in list(positions.items()):
                analysis = next((a for a in analyses if a["symbol"] == symbol), None)
                if analysis and "price" in analysis:
                    current_price = analysis["price"]
                    entry_price = pos["entry_price"]
                    pnl_pct = (current_price - entry_price) / entry_price * 100
                    pnl_value = pos["size"] * (pnl_pct / 100)
                    
                    # Sell conditions: SELL signal OR +3% profit OR -1.5% loss
                    should_sell = (
                        analysis["signal"] == "SELL" or
                        pnl_pct >= 3.0 or
                        pnl_pct <= -1.5
                    )
                    
                    if should_sell:
                        # Simulate sell
                        positions.pop(symbol)
                        available_capital += pos["size"] + pnl_value
                        total_pnl += pnl_value
                        
                        trade = {
                            "time": datetime.now().isoformat(),
                            "action": "SELL",
                            "symbol": symbol,
                            "price": current_price,
                            "pnl": pnl_value,
                            "pnl_pct": pnl_pct
                        }
                        trade_log.append(trade)
                        
                        emoji = "🟢" if pnl_value > 0 else "🔴"
                        print(f"  {emoji} SELL {symbol} @ ${current_price:.2f} | P&L: £{pnl_value:.2f} ({pnl_pct:+.2f}%)")
                    else:
                        print(f"  📊 {symbol}: ${current_price:.2f} | P&L: {pnl_pct:+.2f}%")
            
            print(f"\n💼 Portfolio Summary:")
            print(f"   Open Positions: {len(positions)}")
            print(f"   Available Cash: £{available_capital:.2f}")
            print(f"   Total P&L: £{total_pnl:.2f}")
            print(f"   Total Value: £{available_capital + sum(p['size'] for p in positions.values()):.2f}")
            
            # Wait before next cycle
            print(f"\n⏱️  Next cycle in 30 seconds...")
            await asyncio.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
        print(f"\n📊 Final Results:")
        print(f"   Total Trades: {len(trade_log)}")
        print(f"   Final P&L: £{total_pnl:.2f}")
        print(f"   Return: {(total_pnl / SIMULATED_CAPITAL) * 100:.2f}%")
        
        # Save trade log
        with open("/root/dry_run_trades.json", "w") as f:
            json.dump(trade_log, f, indent=2)
        print(f"\n💾 Trade log saved to /root/dry_run_trades.json")
        
    finally:
        await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
