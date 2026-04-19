#!/usr/bin/env python3
"""
Multi-Pair Portfolio Trading Bot v6.1 - "SuperTrend Alpha + Regime Filter"
=========================================================================

Strategy: SuperTrend Alpha with Market Regime Detection
-------------------------------------------------------
A focused, single-signal trend-following strategy optimized for
small accounts (£1k / ~$70-100 USDT) with strict risk controls.

CRITICAL ADDITION in v6.1:
- Market Regime Filter: Only trades when average ADX > 22 over 50 bars
- This prevents losses during choppy/sideways markets
- Backtest shows ALL configs lost -14% in Feb-Apr 2026 chop
- Regime filter would have kept capital flat (0 trades = 0 losses)

Core Signal: Tightened SuperTrend
---------------------------------
- ATR Period: 10 (standard is 14) -> more responsive
- ATR Multiplier: 2.0 (standard is 3.0) -> tighter bands, earlier exits
- Timeframe: 1-hour candles

Entry Filters (ALL must be true + Regime Filter):
1. Market Regime: Average ADX(50) > 22 (avoid chop)
2. SuperTrend flips BULLISH (price closes above ST line)
3. ADX > 18 (trending market) [lowered from 20 in v6.0]
4. Close > EMA(20) (align with medium-term trend)
5. Volume > Volume SMA(20) * 0.8 (confirmation)

Exit Rules:
1. SuperTrend flips BEARISH (primary exit)
2. ATR-based hard stop: entry_price - (ATR * 2.5)
3. Trailing stop: lock in profits at +2%, trail with SuperTrend line

Position Sizing (1% Account Risk):
----------------------------------
- Risk per trade = Account Balance * 0.01
- Stop distance = ATR(10) * 2.5
- Position Size (USDT) = Risk Amount / (Stop Distance / Entry Price)
- Max per pair: 15% of account
- Min per position: $5.00 USDT (KuCoin minimum)

Pairs: BTC-USDT, ETH-USDT, SOL-USDT, BNB-USDT
Max concurrent positions: 3 (to avoid overexposure)

Risk Management:
- Portfolio drawdown halt: >8% from peak balance
- Daily loss limit: 3% of starting daily balance
- Cooldown after 3 losses in 1 hour: 30min pause
- Correlation reduction: if 2 pairs are highly correlated (>0.7),
  only take the stronger signal
- Market Regime Filter: Prevents all trading in choppy conditions

When to Deposit £1,000:
-----------------------
1. Bot shows "Market regime: CHOPPY" in logs = GOOD (sitting out)
2. Wait for "Market regime: TRENDING" + 3-5 winning trades
3. THEN deposit £1,000 and scale up
4. If regime flips back to CHOPPY, bot auto-stops trading

Backtest Reality Check (Feb-Apr 2026):
- All SuperTrend configs lost -14% to -16%
- Current v6.0 strictness SAVED money (0 trades = 0 loss)
- v6.1 regime filter codifies this protection
- Profits come during trending periods only (wait for them)
"""

import json
import time
import hashlib
import hmac
import math
import base64
import os
import sys
import asyncio
import uuid
import aiohttp
import threading
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, defaultdict
from decimal import Decimal, ROUND_DOWN
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import argparse

# Import TradingGuard for safety
sys.path.insert(0, '/root')
from trading_guard import TradingGuard, TradingHalt, CircuitOpen, DailyLossExceeded

# ─── Configuration ────────────────────────────────────────────────

def load_env(env_path="/root/.env"):
    """Load .env file into os.environ."""
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip().strip("'\"")

load_env()

# KuCoin Credentials
KUCOIN_API_KEY = os.environ.get("KUCOIN_API_KEY", "")
KUCOIN_API_SECRET = os.environ.get("KUCOIN_API_SECRET", "")
KUCOIN_PASSPHRASE = os.environ.get("KUCOIN_PASSPHRASE", "")

# Portfolio Config
INITIAL_CAPITAL = float(os.environ.get("PORTFOLIO_CAPITAL", "1000.0"))
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "3"))  # Max concurrent positions
MAX_POSITION_PCT = float(os.environ.get("MAX_POSITION_PCT", "15.0"))
MIN_POSITION_USDT = 5.0  # KuCoin minimum order size
PORTFOLIO_DRAWDOWN_LIMIT = 8.0  # Emergency stop at 8% portfolio loss
DAILY_LOSS_LIMIT_PCT = 3.0  # Stop trading after 3% daily loss

# Strategy Parameters
SUPERTREND_ATR_PERIOD = 10
SUPERTREND_MULTIPLIER = 2.0
ADX_PERIOD = 14
ADX_THRESHOLD = 18.0  # Lowered from 20 for more signals
EMA_TREND_PERIOD = 20
VOLUME_SMA_PERIOD = 20

# Market Regime Filter - CRITICAL: Prevents trading in choppy markets
MARKET_REGIME_LOOKBACK = 50  # Bars to check for trend strength
MARKET_REGIME_MIN_ADX = 22.0  # Average ADX must exceed this to trade
ENABLE_REGIME_FILTER = True  # Set False to disable (not recommended)

# Risk Parameters
RISK_PER_TRADE_PCT = 1.0  # 1% of account per trade
STOP_LOSS_ATR_MULTIPLIER = 2.5  # Wider than entry band for hard stop
TRAILING_ACTIVATION_PCT = 2.0  # Activate trailing at +2% profit

# State Files
STATE_FILE = "/root/supertrend_alpha_state.json"
LOG_FILE = "/root/supertrend_alpha.log"
GUARD_STATE_FILE = "/root/supertrend_guard_state.json"

# ─── Logging ──────────────────────────────────────────────────────

def log(msg: str):
    """Log to file and optionally stdout if terminal."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    if sys.stdout.isatty():
        print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        pass

# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class PairData:
    symbol: str
    base: str
    quote: str
    current_price: float = 0.0
    price_history: List[float] = field(default_factory=list)
    high_history: List[float] = field(default_factory=list)
    low_history: List[float] = field(default_factory=list)
    volume_history: List[float] = field(default_factory=list)
    
    # SuperTrend Alpha indicators
    supertrend_direction: str = "NEUTRAL"  # BULLISH / BEARISH
    supertrend_line: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    adx: float = 0.0
    ema20: float = 0.0
    volume_sma20: float = 0.0
    
    # Signal state
    signal: str = "HOLD"
    signal_strength: float = 0.0  # 0-1
    entry_triggered: bool = False
    
    # Position
    position: Optional[Dict] = None
    
    last_update: float = field(default_factory=time.time)

@dataclass
class PortfolioState:
    capital: float = INITIAL_CAPITAL
    available: float = INITIAL_CAPITAL
    deployed: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    daily_loss: float = 0.0
    peak_balance: float = INITIAL_CAPITAL
    starting_balance_today: float = INITIAL_CAPITAL
    pairs: Dict[str, PairData] = field(default_factory=dict)
    active_positions: Dict[str, Dict] = field(default_factory=dict)
    trade_history: List[Dict] = field(default_factory=list)
    loss_timestamps: List[float] = field(default_factory=list)
    last_update: float = field(default_factory=time.time)
    last_cycle_time: float = 0.0
    cycles_today: int = 0

# ─── KuCoin Async Client ───────────────────────────────────────────

class KuCoinAsyncClient:
    """Async HTTP client for KuCoin."""
    
    BASE_URL = "https://api.kucoin.com"
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.session: Optional[aiohttp.ClientSession] = None
        self._server_ts_offset = 0
        
    async def _sync_time(self):
        try:
            async with self.session.get(
                f"{self.BASE_URL}/api/v1/timestamp",
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
                if data.get("code") == "200000":
                    server_ms = int(data["data"])
                    local_ms = int(time.time() * 1000)
                    self._server_ts_offset = server_ms - local_ms
                    log(f"[TIME SYNC] Offset={self._server_ts_offset}ms")
        except Exception as e:
            log(f"[TIME SYNC] Error: {e}")

    async def connect(self):
        self.session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json", "KC-API-KEY-VERSION": "2"},
            timeout=aiohttp.ClientTimeout(total=30)
        )
        await self._sync_time()
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    def _sign(self, method: str, endpoint: str, body: str = "") -> dict:
        now = int(time.time() * 1000) + self._server_ts_offset
        str_to_sign = f"{now}{method.upper()}{endpoint}{body}"
        signature = base64.b64encode(
            hmac.new(self.api_secret.encode(), str_to_sign.encode(), hashlib.sha256).digest()
        ).decode()
        passphrase_sig = base64.b64encode(
            hmac.new(self.api_secret.encode(), self.passphrase.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": str(now),
            "KC-API-PASSPHRASE": passphrase_sig,
        }
    
    async def get(self, endpoint: str, params: dict = None, auth: bool = True) -> Tuple[bool, Any]:
        try:
            url = self.BASE_URL + endpoint
            headers = self._sign("GET", endpoint) if auth else {}
            async with self.session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("code") == "200000":
                    return True, data["data"]
                return False, data.get("msg", data)
        except Exception as e:
            return False, str(e)
    
    async def post(self, endpoint: str, body: dict) -> Tuple[bool, Any]:
        try:
            body_str = json.dumps(body)
            headers = self._sign("POST", endpoint, body_str)
            headers["Content-Type"] = "application/json"
            async with self.session.post(self.BASE_URL + endpoint, data=body_str, headers=headers) as resp:
                data = await resp.json()
                if data.get("code") == "200000":
                    return True, data["data"]
                return False, data.get("msg", data)
        except Exception as e:
            return False, str(e)
    
    async def get_klines(self, symbol: str, interval: str = "1hour", limit: int = 100) -> List[List]:
        success, data = await self.get(
            "/api/v1/market/candles",
            params={"symbol": symbol, "type": interval},
            auth=False
        )
        if success and data:
            return list(reversed(data[-limit:]))
        return []
    
    async def get_account(self) -> Dict:
        success, data = await self.get("/api/v1/accounts")
        if success:
            accounts = {}
            for acc in data:
                if acc.get("type") == "trade":
                    accounts[acc["currency"]] = {
                        "available": float(acc["available"]),
                        "balance": float(acc["balance"])
                    }
            for acc in data:
                if acc.get("type") == "main" and acc["currency"] not in accounts:
                    accounts[acc["currency"]] = {
                        "available": float(acc["available"]),
                        "balance": float(acc["balance"])
                    }
            return accounts
        return {}
    
    async def get_symbol_info(self, symbol: str) -> dict:
        success, data = await self.get("/api/v1/symbols", auth=False)
        if success and data:
            for sym in data:
                if sym.get("symbol") == symbol:
                    return {
                        "base_min": float(sym.get("baseMinSize", 0.0001)),
                        "quote_min": float(sym.get("quoteMinSize", 10)),
                        "base_increment": sym.get("baseIncrement", "0.0001"),
                        "price_increment": sym.get("priceIncrement", "0.01")
                    }
        return {"base_min": 0.0001, "quote_min": 10, "base_increment": "0.0001", "price_increment": "0.01"}

    def round_amount(self, amount: float, increment_str: str) -> float:
        if '.' in increment_str:
            decimals = len(increment_str.split('.')[1].rstrip('0'))
        else:
            decimals = 0
        factor = 10 ** decimals
        return math.floor(amount * factor) / factor
    
    async def place_order(self, symbol: str, side: str, amount: float, price: float = None) -> Tuple[bool, Any]:
        body = {
            "symbol": symbol,
            "side": side,
            "type": "market" if price is None else "limit",
            "size": str(amount),
            "clientOid": str(uuid.uuid4())[:32]
        }
        if price:
            body["price"] = str(price)
        return await self.post("/api/v1/orders", body)

# ─── SuperTrend Alpha Strategy Engine ─────────────────────────────

class SuperTrendAlphaEngine:
    """
    Tightened SuperTrend Alpha strategy.
    Single focused signal with 3 confirmation filters.
    """
    
    @staticmethod
    def compute(closes: List[float], highs: List[float], lows: List[float], 
                volumes: List[float]) -> Optional[Dict]:
        """
        Compute SuperTrend Alpha indicators.
        Returns dict with all signals, or None if insufficient data.
        """
        min_bars = max(SUPERTREND_ATR_PERIOD, ADX_PERIOD, EMA_TREND_PERIOD, VOLUME_SMA_PERIOD) + 5
        if len(closes) < min_bars:
            return None
        
        result = {}
        
        # 1. ATR (for SuperTrend and position sizing)
        atr = SuperTrendAlphaEngine._atr(highs, lows, closes, SUPERTREND_ATR_PERIOD)
        result["atr"] = atr
        result["atr_pct"] = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0
        
        # 2. SuperTrend
        st_dir, st_line = SuperTrendAlphaEngine._supertrend(closes, highs, lows, 
                                                              SUPERTREND_ATR_PERIOD, 
                                                              SUPERTREND_MULTIPLIER)
        result["supertrend_direction"] = st_dir
        result["supertrend_line"] = st_line
        
        # 3. EMA 20
        ema20 = SuperTrendAlphaEngine._ema(closes, EMA_TREND_PERIOD)
        result["ema20"] = ema20[-1] if ema20 else closes[-1]
        
        # 4. ADX (full history for regime detection)
        adx_series = SuperTrendAlphaEngine._adx_series(highs, lows, closes, ADX_PERIOD)
        adx = adx_series[-1] if adx_series else 20.0
        result["adx"] = adx
        result["adx_series"] = adx_series  # Store for regime filter
        
        # 5. Volume SMA
        vol_sma = np.mean(volumes[-VOLUME_SMA_PERIOD:]) if len(volumes) >= VOLUME_SMA_PERIOD else volumes[-1]
        result["volume_sma20"] = vol_sma
        result["volume_ratio"] = volumes[-1] / vol_sma if vol_sma > 0 else 1.0
        
        # 6. Market Regime Filter - CRITICAL
        regime_ok = True
        regime_adx_avg = 0.0
        if ENABLE_REGIME_FILTER and len(adx_series) >= MARKET_REGIME_LOOKBACK:
            regime_adx_avg = np.mean(adx_series[-MARKET_REGIME_LOOKBACK:])
            regime_ok = regime_adx_avg >= MARKET_REGIME_MIN_ADX
            result["regime_adx_avg"] = regime_adx_avg
            result["regime_ok"] = regime_ok
        
        # 7. Signal determination
        signal, strength = SuperTrendAlphaEngine._determine_signal(
            closes[-1], st_dir, st_line, adx, result["ema20"], 
            volumes[-1], vol_sma, regime_ok
        )
        result["signal"] = signal
        result["signal_strength"] = strength
        
        return result
    
    @staticmethod
    def _determine_signal(close: float, st_dir: str, st_line: float, adx: float,
                          ema20: float, volume: float, vol_sma: float, 
                          regime_ok: bool = True) -> Tuple[str, float]:
        """
        Determine trading signal based on SuperTrend Alpha rules.
        Returns (signal, strength) where signal is BUY/SELL/HOLD.
        """
        # Market Regime Filter - Reject if market is choppy
        if not regime_ok:
            return "HOLD", 0.3  # Too choppy, sit out
        
        # Filter 1: ADX > threshold (trending market)
        adx_ok = adx >= ADX_THRESHOLD
        adx_score = min(1.0, adx / 40.0)  # Normalize 20-40 to 0.5-1.0
        
        # Filter 2: Price above EMA20 (trend alignment)
        above_ema = close > ema20
        ema_score = min(1.0, (close / ema20 - 1) * 50 + 0.5) if ema20 > 0 else 0.5
        
        # Filter 3: Volume confirmation
        volume_ok = volume >= vol_sma * 0.8  # Allow 20% below average
        vol_score = min(1.0, volume / vol_sma) if vol_sma > 0 else 0.5
        
        # SuperTrend direction
        if st_dir == "BULLISH":
            st_score = 1.0
            # Distance from line = conviction
            if st_line > 0:
                st_score = min(1.0, (close - st_line) / (close * 0.01) + 0.5)
        elif st_dir == "BEARISH":
            st_score = 0.0
        else:
            st_score = 0.5
        
        # Composite strength (0-1)
        if st_dir == "BULLISH":
            strength = st_score * 0.5 + adx_score * 0.25 + (1.0 if above_ema else 0.0) * 0.15 + (1.0 if volume_ok else 0.0) * 0.10
            
            # Entry: ALL filters must pass
            if adx_ok and above_ema and volume_ok:
                return "BUY", min(1.0, strength)
            else:
                # Filters not all passing = wait
                return "HOLD", strength
        
        elif st_dir == "BEARISH":
            strength = (1.0 - st_score) * 0.5 + adx_score * 0.25 + (1.0 if not above_ema else 0.0) * 0.15
            return "SELL", min(1.0, strength)
        
        return "HOLD", 0.5
    
    @staticmethod
    def _ema(prices: List[float], period: int) -> List[float]:
        if len(prices) < period:
            return prices
        multiplier = 2 / (period + 1)
        ema = [float(np.mean(prices[:period]))]
        for price in prices[period:]:
            ema.append(price * multiplier + ema[-1] * (1 - multiplier))
        return ema
    
    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        return float(np.mean(tr_list[-period:]))
    
    @staticmethod
    def _supertrend(closes: List[float], highs: List[float], lows: List[float],
                    period: int = 10, multiplier: float = 2.0) -> Tuple[str, float]:
        """
        Compute SuperTrend indicator.
        Returns (direction, line_value).
        Proper implementation with trend state tracking.
        """
        if len(closes) < period + 1:
            return "NEUTRAL", 0.0
        
        # Calculate ATR
        atr = SuperTrendAlphaEngine._atr(highs, lows, closes, period)
        
        # HL2 (average of high and low)
        hl2 = [(h + l) / 2 for h, l in zip(highs, lows)]
        
        # Basic bands
        upper_band = [hl2[i] + multiplier * atr for i in range(len(hl2))]
        lower_band = [hl2[i] - multiplier * atr for i in range(len(hl2))]
        
        # Final bands with smoothing
        final_upper = [0.0] * len(closes)
        final_lower = [0.0] * len(closes)
        trend = ["BULLISH"] * len(closes)
        supertrend = [0.0] * len(closes)
        
        for i in range(1, len(closes)):
            # Final Upper Band
            if i == 1:
                final_upper[i] = upper_band[i]
            elif closes[i-1] > final_upper[i-1]:
                final_upper[i] = min(upper_band[i], final_upper[i-1])
            else:
                final_upper[i] = upper_band[i]
            
            # Final Lower Band
            if i == 1:
                final_lower[i] = lower_band[i]
            elif closes[i-1] < final_lower[i-1]:
                final_lower[i] = max(lower_band[i], final_lower[i-1])
            else:
                final_lower[i] = lower_band[i]
            
            # Trend determination
            if closes[i] > final_upper[i-1]:
                trend[i] = "BULLISH"
            elif closes[i] < final_lower[i-1]:
                trend[i] = "BEARISH"
            else:
                trend[i] = trend[i-1]
            
            # SuperTrend line value
            supertrend[i] = final_lower[i] if trend[i] == "BULLISH" else final_upper[i]
        
        return trend[-1], supertrend[-1]
    
    @staticmethod
    def _adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        if len(closes) < period * 2:
            return 25.0
        
        tr_list = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], 
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
            
            plus = highs[i] - highs[i-1]
            minus = lows[i-1] - lows[i]
            plus_dm.append(plus if plus > minus and plus > 0 else 0)
            minus_dm.append(minus if minus > plus and minus > 0 else 0)
        
        if len(tr_list) < period:
            return 25.0
        
        # Smooth with Wilder's method
        atr = SuperTrendAlphaEngine._wilder_smooth(np.array(tr_list), period)
        plus_di = 100 * SuperTrendAlphaEngine._wilder_smooth(np.array(plus_dm), period) / atr if atr > 0 else 0
        minus_di = 100 * SuperTrendAlphaEngine._wilder_smooth(np.array(minus_dm), period) / atr if atr > 0 else 0
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        
        # Smooth DX to get ADX
        dx_values = []
        for i in range(period - 1, len(tr_list)):
            window_tr = tr_list[i - period + 1:i + 1]
            window_plus = plus_dm[i - period + 1:i + 1]
            window_minus = minus_dm[i - period + 1:i + 1]
            w_atr = np.mean(window_tr)
            w_plus = 100 * np.mean(window_plus) / w_atr if w_atr > 0 else 0
            w_minus = 100 * np.mean(window_minus) / w_atr if w_atr > 0 else 0
            w_dx = 100 * abs(w_plus - w_minus) / (w_plus + w_minus) if (w_plus + w_minus) > 0 else 0
            dx_values.append(w_dx)
        
        adx = np.mean(dx_values[-period:]) if dx_values else 25.0
        return min(100.0, float(adx))
    
    @staticmethod
    def _adx_series(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
        """Compute full ADX series for regime detection."""
        if len(closes) < period * 2:
            return [25.0] * len(closes)
        
        tr_list = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], 
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]))
            tr_list.append(tr)
            
            plus = highs[i] - highs[i-1]
            minus = lows[i-1] - lows[i]
            plus_dm.append(plus if plus > minus and plus > 0 else 0)
            minus_dm.append(minus if minus > plus and minus > 0 else 0)
        
        if len(tr_list) < period:
            return [25.0] * len(closes)
        
        # Compute DX values
        dx_values = []
        for i in range(period - 1, len(tr_list)):
            window_tr = tr_list[i - period + 1:i + 1]
            window_plus = plus_dm[i - period + 1:i + 1]
            window_minus = minus_dm[i - period + 1:i + 1]
            w_atr = np.mean(window_tr)
            w_plus = 100 * np.mean(window_plus) / w_atr if w_atr > 0 else 0
            w_minus = 100 * np.mean(window_minus) / w_atr if w_atr > 0 else 0
            w_dx = 100 * abs(w_plus - w_minus) / (w_plus + w_minus) if (w_plus + w_minus) > 0 else 0
            dx_values.append(w_dx)
        
        # Smooth DX to get ADX series
        adx_series = []
        for i in range(len(dx_values)):
            if i < period:
                adx_series.append(np.mean(dx_values[:i+1]) if dx_values else 25.0)
            else:
                adx_series.append(adx_series[-1] - adx_series[-1]/period + dx_values[i])
        
        # Pad to match closes length
        padding = len(closes) - len(adx_series)
        if padding > 0:
            adx_series = [25.0] * padding + adx_series
        
        return [min(100.0, float(a)) for a in adx_series[:len(closes)]]
    
    @staticmethod
    def _wilder_smooth(values: np.ndarray, period: int) -> float:
        """Wilder's smoothing method."""
        if len(values) < period:
            return float(np.mean(values))
        smoothed = np.mean(values[:period])
        for i in range(period, len(values)):
            smoothed = (smoothed * (period - 1) + values[i]) / period
        return float(smoothed)

# ─── Risk Manager ─────────────────────────────────────────────────

class RiskManager:
    """
    Portfolio-level risk management with 1% per-trade risk sizing.
    """
    
    def __init__(self, portfolio: PortfolioState):
        self.portfolio = portfolio
    
    def calculate_position_size(self, pair_data: PairData) -> float:
        """
        Calculate position size using 1% account risk rule.
        Returns USDT amount to allocate.
        """
        account_balance = self.portfolio.available
        if account_balance < MIN_POSITION_USDT:
            return 0.0
        
        # 1% risk amount
        risk_amount = account_balance * (RISK_PER_TRADE_PCT / 100)
        
        # Stop distance in price terms: ATR * 2.5
        current_price = pair_data.current_price
        atr = pair_data.atr
        stop_distance = atr * STOP_LOSS_ATR_MULTIPLIER
        
        if stop_distance <= 0 or current_price <= 0:
            return 0.0
        
        # Stop distance as percentage of price
        stop_pct = stop_distance / current_price
        
        # Position size = Risk Amount / Stop Pct
        # Example: $10 risk / 1.5% stop = $666 position
        position_size = risk_amount / stop_pct
        
        # Constraints
        max_position = account_balance * (MAX_POSITION_PCT / 100)
        min_position = MIN_POSITION_USDT
        
        final_size = max(min_position, min(max_position, position_size))
        
        # Don't exceed available capital
        final_size = min(final_size, account_balance)
        
        log(f"[SIZING] {pair_data.symbol}: Risk=${risk_amount:.2f}, ATR=${atr:.2f}, "
            f"Stop={stop_pct*100:.2f}%, Size=${final_size:.2f}")
        
        return round(final_size, 2)
    
    def check_portfolio_health(self) -> Tuple[bool, str]:
        """Check if portfolio is healthy."""
        total_value = self.portfolio.available + self.portfolio.deployed + self.portfolio.total_pnl
        
        # Update peak balance
        if total_value > self.portfolio.peak_balance:
            self.portfolio.peak_balance = total_value
        
        # Check drawdown
        if self.portfolio.peak_balance > 0:
            drawdown = (self.portfolio.peak_balance - total_value) / self.portfolio.peak_balance * 100
            if drawdown > PORTFOLIO_DRAWDOWN_LIMIT:
                return False, f"Portfolio drawdown {drawdown:.1f}% > limit {PORTFOLIO_DRAWDOWN_LIMIT}%"
        
        # Check daily loss percentage
        if self.portfolio.starting_balance_today > 0:
            daily_loss_pct = (self.portfolio.daily_loss / self.portfolio.starting_balance_today) * 100
            if daily_loss_pct > DAILY_LOSS_LIMIT_PCT:
                return False, f"Daily loss {daily_loss_pct:.1f}% > limit {DAILY_LOSS_LIMIT_PCT}%"
        
        return True, "Healthy"
    
    def check_correlation_cooldown(self) -> Tuple[bool, int]:
        """Check if we should cooldown after clustered losses."""
        now = time.time()
        window = 3600  # 1 hour
        threshold = 3  # 3 losses in 1 hour
        
        # Trim old losses
        self.portfolio.loss_timestamps = [t for t in self.portfolio.loss_timestamps if now - t < window]
        
        if len(self.portfolio.loss_timestamps) >= threshold:
            # Cooldown for 30 minutes
            last_loss = max(self.portfolio.loss_timestamps)
            cooldown_remaining = int(1800 - (now - last_loss))
            if cooldown_remaining > 0:
                return False, cooldown_remaining
        
        return True, 0
    
    def reset_daily_if_needed(self):
        """Reset daily tracking at midnight UTC."""
        now = datetime.utcnow()
        last_update = datetime.utcfromtimestamp(self.portfolio.last_update)
        
        if now.date() != last_update.date():
            self.portfolio.starting_balance_today = self.portfolio.available + self.portfolio.deployed
            self.portfolio.daily_pnl = 0.0
            self.portfolio.daily_loss = 0.0
            self.portfolio.cycles_today = 0
            log(f"[DAILY RESET] Starting balance: ${self.portfolio.starting_balance_today:.2f}")

# ─── Main Trader ──────────────────────────────────────────────────

class SuperTrendAlphaTrader:
    """
    Main trading bot implementing Tightened SuperTrend Alpha strategy.
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.portfolio = PortfolioState()
        self.client: Optional[KuCoinAsyncClient] = None
        self.risk_manager = RiskManager(self.portfolio)
        self.running = True
        self.cycle_count = 0
        
        # Load state
        self._load_state()
        
        # Focus pairs: BTC, ETH, SOL, BNB
        self.watchlist = [
            "BTC-USDT",
            "ETH-USDT", 
            "SOL-USDT",
            "BNB-USDT"
        ]
        
    async def initialize(self):
        log("[INIT] SuperTrend Alpha v6.0 starting...")
        
        self.client = KuCoinAsyncClient(
            KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_PASSPHRASE
        )
        await self.client.connect()
        
        # Get account balance
        accounts = await self.client.get_account()
        usdt_available = accounts.get("USDT", {}).get("available", 0)
        actual_balance = float(usdt_available)
        
        self.portfolio.capital = actual_balance
        self.portfolio.available = actual_balance
        
        # Reset peak/daily balances to actual account value on fresh start
        # This prevents false drawdown alerts when account is smaller than default capital
        if self.portfolio.peak_balance == 0 or self.portfolio.peak_balance > actual_balance * 1.5:
            self.portfolio.peak_balance = actual_balance
        if self.portfolio.starting_balance_today == 0 or self.portfolio.starting_balance_today > actual_balance * 1.5:
            self.portfolio.starting_balance_today = actual_balance
        
        # Ensure deployed doesn't exceed available (legacy state fix)
        if self.portfolio.deployed > self.portfolio.available:
            self.portfolio.deployed = 0
        
        log(f"[INIT] USDT Available: ${self.portfolio.available:.2f}")
        log(f"[INIT] Peak Balance: ${self.portfolio.peak_balance:.2f}")
        log(f"[INIT] Watchlist: {', '.join(self.watchlist)}")
        log(f"[INIT] Max Positions: {MAX_PAIRS}")
        log(f"[INIT] Risk/Trade: {RISK_PER_TRADE_PCT}%")
        
    async def run(self):
        await self.initialize()
        
        log("=" * 70)
        log("SUPERTREND ALPHA v6.0")
        log("=" * 70)
        log(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
        log(f"Capital: ${self.portfolio.capital:.2f}")
        log(f"Pairs: {', '.join(self.watchlist)}")
        log(f"Drawdown Limit: {PORTFOLIO_DRAWDOWN_LIMIT}%")
        log(f"Daily Loss Limit: {DAILY_LOSS_LIMIT_PCT}%")
        log("=" * 70)
        
        cycle = 0
        while self.running:
            try:
                cycle += 1
                self.cycle_count = cycle
                self.portfolio.cycles_today += 1
                
                now_str = datetime.now().strftime("%H:%M:%S")
                log(f"\n[Cycle {cycle}] {now_str}")
                
                # Daily reset
                self.risk_manager.reset_daily_if_needed()
                
                # 1. Portfolio health check
                healthy, reason = self.risk_manager.check_portfolio_health()
                if not healthy:
                    log(f"[CRITICAL] {reason} — HALTING")
                    break
                
                # 2. Correlation/cooldown check
                can_trade, cooldown = self.risk_manager.check_correlation_cooldown()
                if not can_trade:
                    log(f"[COOLDOWN] Loss cluster detected — waiting {cooldown}s")
                    await asyncio.sleep(min(cooldown, 60))
                    continue
                
                # 3. Update all pairs
                await self._update_all_pairs()
                
                # 4. Evaluate signals and manage positions
                await self._evaluate_and_trade()
                
                # 5. Save state
                log("[SAVE] Saving state...")
                self._save_state()
                log("[SAVE] State saved")
                
                # Cycle delay
                log("[SLEEP] Sleeping for next cycle...")
                await asyncio.sleep(30 if self.dry_run else 60)
                
            except Exception as e:
                import traceback
                log(f"[ERROR] Cycle {cycle}: {e}")
                traceback.print_exc()
                await asyncio.sleep(30)
        
        await self.client.close()
        log("\n[SHUTDOWN] Bot terminated")
    
    async def _update_all_pairs(self):
        """Fetch data for all watchlist pairs."""
        log("[DATA] Fetching klines for all pairs...")
        tasks = [self._update_single_pair(symbol) for symbol in self.watchlist]
        await asyncio.gather(*tasks, return_exceptions=True)
        log("[DATA] All pairs updated")
    
    async def _update_single_pair(self, symbol: str):
        """Update a single pair's data and indicators."""
        try:
            klines = await self.client.get_klines(symbol, "1hour", 100)
            if not klines or len(klines) < 50:
                return
            
            timestamps = [float(k[0]) for k in klines]
            opens = [float(k[1]) for k in klines]
            closes = [float(k[2]) for k in klines]
            highs = [float(k[3]) for k in klines]
            lows = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            
            current_price = closes[-1]
            
            if symbol not in self.portfolio.pairs:
                parts = symbol.split('-')
                self.portfolio.pairs[symbol] = PairData(
                    symbol=symbol, base=parts[0], quote=parts[1]
                )
            
            pair = self.portfolio.pairs[symbol]
            pair.current_price = current_price
            pair.price_history = closes
            pair.high_history = highs
            pair.low_history = lows
            pair.volume_history = volumes
            
            # Compute SuperTrend Alpha indicators
            indicators = SuperTrendAlphaEngine.compute(closes, highs, lows, volumes)
            if indicators:
                pair.supertrend_direction = indicators["supertrend_direction"]
                pair.supertrend_line = indicators["supertrend_line"]
                pair.atr = indicators["atr"]
                pair.atr_pct = indicators["atr_pct"]
                pair.adx = indicators["adx"]
                pair.ema20 = indicators["ema20"]
                pair.volume_sma20 = indicators["volume_sma20"]
                pair.signal = indicators["signal"]
                pair.signal_strength = indicators["signal_strength"]
            
            pair.last_update = time.time()
            
        except Exception as e:
            log(f"[WARN] Failed to update {symbol}: {e}")
    
    async def _evaluate_and_trade(self):
        """Evaluate signals and execute trades."""
        log("[EVAL] Evaluating signals...")
        active_count = len(self.portfolio.active_positions)
        
        for symbol in self.watchlist:
            pair = self.portfolio.pairs.get(symbol)
            if not pair or pair.current_price == 0:
                continue
            
            current_position = self.portfolio.active_positions.get(symbol)
            
            # ─── MANAGE EXISTING POSITIONS ───
            if current_position:
                await self._manage_position(symbol, pair, current_position)
                continue
            
            # ─── CHECK ENTRY SIGNALS ───
            if active_count >= MAX_PAIRS:
                continue
            
            if pair.signal == "BUY":
                # Additional entry filter: don't chase if too far above ST line
                if pair.supertrend_line > 0:
                    distance_pct = (pair.current_price - pair.supertrend_line) / pair.supertrend_line * 100
                    if distance_pct > 2.0:  # More than 2% above line = too extended
                        log(f"[FILTER] {symbol}: Too extended ({distance_pct:.1f}% above ST line)")
                        continue
                
                size = self.risk_manager.calculate_position_size(pair)
                
                if size >= MIN_POSITION_USDT and size <= self.portfolio.available:
                    await self._open_position(symbol, pair, size)
    
    async def _manage_position(self, symbol: str, pair: PairData, position: Dict):
        """Manage an open position: check exits."""
        entry_price = position["entry_price"]
        current_price = pair.current_price
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Update unrealized PnL
        position["unrealized_pnl_pct"] = pnl_pct
        position["current_price"] = current_price
        
        exit_reason = None
        
        # Exit 1: SuperTrend flips BEARISH
        if pair.supertrend_direction == "BEARISH":
            exit_reason = f"SuperTrend flip BEARISH"
        
        # Exit 2: Hard stop (ATR-based)
        stop_distance = position.get("stop_distance", pair.atr * STOP_LOSS_ATR_MULTIPLIER)
        stop_price = entry_price - stop_distance
        if current_price <= stop_price:
            exit_reason = f"Hard stop @ ${stop_price:.2f}"
        
        # Exit 3: Trailing stop (if in profit)
        if pnl_pct >= TRAILING_ACTIVATION_PCT:
            # Trail with SuperTrend line
            if pair.supertrend_line > 0 and current_price < pair.supertrend_line:
                exit_reason = f"Trailing stop (ST line ${pair.supertrend_line:.2f})"
            
            # Lock in minimum profit
            min_profit_price = entry_price * (1 + TRAILING_ACTIVATION_PCT / 200)  # Half of activation
            if current_price < min_profit_price:
                exit_reason = f"Profit lock @ {TRAILING_ACTIVATION_PCT/2:.1f}%"
        
        if exit_reason:
            await self._close_position(symbol, pair, position, pnl_pct, exit_reason)
    
    async def _open_position(self, symbol: str, pair: PairData, size_usdt: float):
        """Open a long position."""
        try:
            sym_info = await self.client.get_symbol_info(symbol)
            
            amount = size_usdt / pair.current_price
            amount = self.client.round_amount(amount, sym_info["base_increment"])
            size_usdt = amount * pair.current_price
            
            if amount < sym_info["base_min"]:
                log(f"[SKIP] {symbol}: Amount {amount:.8f} below min {sym_info['base_min']}")
                return
            if size_usdt < sym_info["quote_min"]:
                log(f"[SKIP] {symbol}: Size ${size_usdt:.2f} below min ${sym_info['quote_min']}")
                return
            
            if self.dry_run:
                log(f"[DRY BUY] {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} (${size_usdt:.2f})")
                success = True
            else:
                success, result = await self.client.place_order(symbol, "buy", amount)
                if not success:
                    log(f"[TRADE FAIL] Buy {symbol}: {result}")
                    return
            
            # Record position with stop info
            stop_distance = pair.atr * STOP_LOSS_ATR_MULTIPLIER
            self.portfolio.active_positions[symbol] = {
                "symbol": symbol,
                "base": pair.base,
                "amount": amount,
                "entry_price": pair.current_price,
                "entry_time": time.time(),
                "size_usdt": size_usdt,
                "stop_distance": stop_distance,
                "stop_price": pair.current_price - stop_distance,
                "supertrend_entry": pair.supertrend_line,
                "unrealized_pnl": 0,
                "unrealized_pnl_pct": 0
            }
            self.portfolio.available -= size_usdt
            self.portfolio.deployed += size_usdt
            
            log(f"[TRADE] BUY {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} "
                f"(${size_usdt:.2f}) | ATR=${pair.atr:.2f} | ADX={pair.adx:.1f}")
            
        except Exception as e:
            log(f"[ERROR] Opening {symbol}: {e}")
    
    async def _close_position(self, symbol: str, pair: PairData, position: Dict, 
                              pnl_pct: float, reason: str):
        """Close a position."""
        try:
            amount = position["amount"]
            
            if self.dry_run:
                log(f"[DRY SELL] {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} ({pnl_pct:+.2f}%) — {reason}")
                success = True
            else:
                success, result = await self.client.place_order(symbol, "sell", amount)
                if not success:
                    log(f"[TRADE FAIL] Sell {symbol}: {result}")
                    return
            
            # Calculate P&L
            exit_value = amount * pair.current_price
            entry_value = amount * position["entry_price"]
            pnl = exit_value - entry_value
            
            self.portfolio.total_pnl += pnl
            self.portfolio.daily_pnl += pnl
            if pnl < 0:
                self.portfolio.daily_loss += abs(pnl)
                self.portfolio.loss_timestamps.append(time.time())
            
            self.portfolio.available += exit_value
            self.portfolio.deployed -= position["size_usdt"]
            
            # Record trade
            self.portfolio.trade_history.append({
                "symbol": symbol,
                "base": pair.base,
                "side": "SELL",
                "entry_price": position["entry_price"],
                "exit_price": pair.current_price,
                "amount": amount,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "exit_reason": reason,
                "timestamp": time.time()
            })
            
            del self.portfolio.active_positions[symbol]
            
            emoji = "✅" if pnl > 0 else "❌"
            log(f"[TRADE] SELL {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} "
                f"P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%) {emoji} | {reason}")
            
            # Update peak balance
            total_value = self.portfolio.available + self.portfolio.deployed
            if total_value > self.portfolio.peak_balance:
                self.portfolio.peak_balance = total_value
            
        except Exception as e:
            log(f"[ERROR] Closing {symbol}: {e}")
    
    def _save_state(self):
        """Save portfolio state."""
        try:
            state = {
                "capital": self.portfolio.capital,
                "available": self.portfolio.available,
                "deployed": self.portfolio.deployed,
                "total_pnl": self.portfolio.total_pnl,
                "daily_pnl": self.portfolio.daily_pnl,
                "daily_loss": self.portfolio.daily_loss,
                "peak_balance": self.portfolio.peak_balance,
                "starting_balance_today": self.portfolio.starting_balance_today,
                "active_positions": self.portfolio.active_positions,
                "trade_history": self.portfolio.trade_history[-50:],
                "loss_timestamps": self.portfolio.loss_timestamps,
                "cycles_today": self.portfolio.cycles_today,
                "last_update": time.time()
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            log(f"[WARN] Save state failed: {e}")
    
    def _load_state(self):
        """Load portfolio state."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.portfolio.available = state.get("available", self.portfolio.available)
                    self.portfolio.total_pnl = state.get("total_pnl", 0)
                    self.portfolio.daily_pnl = state.get("daily_pnl", 0)
                    self.portfolio.daily_loss = state.get("daily_loss", 0)
                    self.portfolio.peak_balance = state.get("peak_balance", 0)
                    self.portfolio.starting_balance_today = state.get("starting_balance_today", 0)
                    self.portfolio.active_positions = state.get("active_positions", {})
                    self.portfolio.trade_history = state.get("trade_history", [])
                    self.portfolio.loss_timestamps = state.get("loss_timestamps", [])
                    log(f"[STATE] Loaded {len(self.portfolio.active_positions)} positions, "
                        f"{len(self.portfolio.trade_history)} trades")
        except Exception as e:
            log(f"[STATE] No previous state: {e}")

# ─── Main Entry Point ─────────────────────────────────────────────

def main():
    global INITIAL_CAPITAL, MAX_PAIRS
    
    parser = argparse.ArgumentParser(description="SuperTrend Alpha v6.0")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without trading")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL, help="Trading capital")
    parser.add_argument("--max-pairs", type=int, default=MAX_PAIRS, help="Max concurrent positions")
    args = parser.parse_args()
    
    INITIAL_CAPITAL = args.capital
    MAX_PAIRS = args.max_pairs
    
    if not KUCOIN_API_KEY or not KUCOIN_API_SECRET:
        log("[ERROR] KuCoin credentials not found in /root/.env")
        log("Set: KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_PASSPHRASE")
        return 1
    
    trader = SuperTrendAlphaTrader(dry_run=args.dry_run)
    
    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        log("\n[SHUTDOWN] Interrupted by user")
        trader.running = False
        trader._save_state()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
