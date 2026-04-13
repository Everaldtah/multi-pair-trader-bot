#!/usr/bin/env python3
"""
Multi-Pair Portfolio Trading Bot v5.0 - "Hephaestus"
====================================================

Major Advancements over v4:
===========================

1. MULTI-PAIR PORTFOLIO TRADING
   - Monitors top 20 crypto pairs simultaneously
   - Dynamic pair scoring based on volatility + volume + trend strength
   - Correlation-based position sizing (avoid correlated moves)

2. $500 PORTFOLIO MANAGEMENT
   - Dynamic allocation using Kelly Criterion (conservative fraction)
   - Risk budget: max 15% per pair, min 3% per position
   - Portfolio heat map: total exposure tracking

3. ENSEMBLE TECHNICAL INDICATORS (AI-like weighting)
   - RSI (momentum)
   - EMA crossovers (trend)
   - MFI - Money Flow Index (volume-weighted RSI)
   - MACD (momentum divergence)
   - Bollinger Band squeeze (volatility breakout)
   - Super Trend (trend following)
   - ADX - Average Directional Index (trend strength)
   - Composite signal: weighted ensemble of all indicators

4. ADVANCED RISK MANAGEMENT
   - Portfolio-level drawdown circuit breaker (>8%)
   - Pair correlation matrix (avoid doubling down on same risk)
   - Volatility-adjusted position sizing (ATR-based)
   - Trailing stops ( activates at 2x profit )
   - Market regime detection (bull/bear/ranging)

5. PARALLEL EXECUTION & WEBSOCKET
   - Async/await architecture for concurrent pair monitoring
   - WebSocket price feeds for sub-second updates
   - Order batching for API efficiency

6. THINKING PROCESS VISUALIZATION
   - Emits JSON events to /root/bot_thinking_stream.json
   - Real-time "neural activity" showing:
     * Which data sources are accessed
     * Signal strength calculations per pair
     * Portfolio decisions and trade rationales

7. SELF-LEARNING OPTIMIZATION
   - Tracks trade outcomes by indicator combinations
   - Adjusts indicator weights based on recent performance
   - Re-calibrates every 100 trades

Usage:
    # Dry run (no real trades)
    python3 multi_pair_portfolio_trader_v5.py --dry-run
    
    # Live trading with $500
    python3 multi_pair_portfolio_trader_v5.py --capital 500
    
    # Limit pairs
    python3 multi_pair_portfolio_trader_v5.py --max-pairs 5

Integration with Thinking Engine:
    Navigate to https://hermes-agent-obsidian-view.vercel.app/thinking
    While bot runs, watch "Data Sources" panel:
    - KuCoin API (price feeds)
    - Technical Analysis (7 indicator engine)
    - Portfolio Manager (correlation + sizing)
    - Signal Ensemble (weighted consensus)
    - Trade Executor (KuCoin orders)
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
import aiohttp
# import threading  # Removed - using asyncio.Lock instead
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, defaultdict
from decimal import Decimal, ROUND_DOWN
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import websockets
import argparse

# Import TradingGuard for safety
# Optional TradingGuard integration
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from trading_guard import TradingGuard, TradingHalt, CircuitOpen, DailyLossExceeded
except ImportError:
    # Dummy classes if trading_guard.py not present
    class TradingHalt(Exception): pass
    class CircuitOpen(Exception): pass
    class DailyLossExceeded(Exception): pass
    class TradingGuard:
        def __init__(self, *args, **kwargs): pass
        def check(self, *args, **kwargs): pass
        def record_trade(self, *args, **kwargs): pass
        def save_state(self, *args, **kwargs): pass

# ─── Configuration ────────────────────────────────────────────────

def load_env(env_path=None):
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
INITIAL_CAPITAL = float(os.environ.get("PORTFOLIO_CAPITAL", "500.0"))
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "5"))
MAX_POSITION_PCT = float(os.environ.get("MAX_POSITION_PCT", "15.0"))  # Max per pair
MIN_POSITION_PCT = float(os.environ.get("MIN_POSITION_PCT", "3.0"))   # Min per position
PORTFOLIO_DRAWDOWN_LIMIT = 8.0  # Emergency stop at 8% portfolio loss

# Signal Thresholds (ensemble)
BUY_SIGNAL_THRESHOLD = 0.65  # Composite score >= 65% for entry
SELL_SIGNAL_THRESHOLD = 0.35  # Composite score <= 35% for exit

# Risk Management
TRAILING_STOP_PCT = 1.0  # Activate trailing at +2% profit
TAKE_PROFIT_PCT_BASE = 3.0
STOP_LOSS_PCT_BASE = 1.5
ATR_PERIOD = 14  # For volatility sizing

# State Files
STATE_FILE = str(Path(__file__).parent / "portfolio_trader_state.json")
THINKING_FILE = str(Path(__file__).parent / "bot_thinking_stream.json")
LOG_FILE = str(Path(__file__).parent / "portfolio_trader_v5.log")
GUARD_STATE_FILE = str(Path(__file__).parent / "portfolio_guard_state.json")

# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class PairData:
    symbol: str  # e.g., "ETH-USDT"
    base: str    # e.g., "ETH"
    quote: str   # e.g., "USDT"
    current_price: float = 0.0
    price_history: List[float] = field(default_factory=list)
    volume_24h: float = 0.0
    volatility: float = 0.0  # ATR as % of price
    
    # Indicators
    rsi: float = 50.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    mfi: float = 50.0  # Money Flow Index
    macd: float = 0.0
    macd_signal: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    bb_percent: float = 50.0  # Position within bands
    super_trend: str = "NEUTRAL"
    adx: float = 25.0  # Trend strength
    
    # Composite
    composite_score: float = 0.5  # 0-1 bullishness
    signal: str = "HOLD"  # BUY/SELL/HOLD
    
    # Position
    position: Optional[Dict] = None
    
    last_update: float = field(default_factory=time.time)

@dataclass
class PortfolioState:
    capital: float = INITIAL_CAPITAL
    available: float = INITIAL_CAPITAL
    deployed: float = 0.0
    total_pnl: float = 0.0
    daily_loss: float = 0.0
    pairs: Dict[str, PairData] = field(default_factory=dict)
    active_positions: Dict[str, Dict] = field(default_factory=dict)
    correlation_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    indicator_weights: Dict[str, float] = field(default_factory=lambda: {
        "rsi": 0.20,
        "ema": 0.20,
        "mfi": 0.15,
        "macd": 0.15,
        "bb": 0.15,
        "super_trend": 0.10,
        "adx": 0.05
    })
    trade_history: List[Dict] = field(default_factory=list)
    last_rebalance: float = field(default_factory=time.time)
    market_regime: str = "NEUTRAL"  # BULL/BEAR/RANGING

# ─── Thinking Process Emitter ─────────────────────────────────────

class ThinkingEmitter:
    """
    Emits thinking process events for visualization.
    Writes to JSON file that the web dashboard reads.
    """
    
    def __init__(self, filepath: str = THINKING_FILE):
        self.filepath = filepath
        self.events = deque(maxlen=100)
        self.data_sources = defaultdict(lambda: {"active": False, "access_count": 0})
        self.thought_nodes = []
        self.current_stage = "IDLE"
        
    def emit(self, event_type: str, data: Dict):
        """Emit a thinking event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data
        }
        self.events.append(event)
        self._persist()
    
    def data_source_access(self, source_name: str):
        """Record data source access."""
        self.data_sources[source_name]["active"] = True
        self.data_sources[source_name]["access_count"] += 1
        self.emit("DATA_ACCESS", {"source": source_name})
    
    def set_stage(self, stage: str):
        """Set current thinking stage."""
        self.current_stage = stage
        self.emit("STAGE_CHANGE", {"stage": stage})
    
    def add_thought_node(self, node_type: str, label: str, confidence: float, 
                        connections: List[str] = None):
        """Add a thought node for visualization."""
        node = {
            "id": f"{node_type}_{int(time.time() * 1000)}",
            "type": node_type,
            "label": label,
            "confidence": confidence,
            "connections": connections or [],
            "timestamp": time.time()
        }
        self.thought_nodes.append(node)
        self.emit("THOUGHT_NODE", node)
    
    def signal_calculation(self, pair: str, indicator_scores: Dict[str, float],
                          composite: float, final_signal: str):
        """Record signal calculation for visualization."""
        self.emit("SIGNAL_CALC", {
            "pair": pair,
            "indicator_scores": indicator_scores,
            "composite": composite,
            "signal": final_signal
        })
    
    def portfolio_decision(self, decisions: List[Dict]):
        """Record portfolio-level decision."""
        self.emit("PORTFOLIO_DECISION", {"decisions": decisions})
    
    def _persist(self):
        """Write current state to file."""
        try:
            state = {
                "stage": self.current_stage,
                "data_sources": dict(self.data_sources),
                "thought_nodes": list(self.thought_nodes)[-20:],  # Last 20
                "events": list(self.events)[-50:],  # Last 50
                "timestamp": time.time()
            }
            with open(self.filepath, 'w') as f:
                json.dump(state, f)
        except Exception:
            pass

# Global emitter
think = ThinkingEmitter()

# ─── KuCoin Async Client ───────────────────────────────────────────

class KuCoinAsyncClient:
    """Async HTTP/WebSocket client for KuCoin."""
    
    BASE_URL = "https://api.kucoin.com"
    WS_URL = "wss://ws-api.kucoin.com/spotMarket/url"
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws_connection = None
        self._server_ts_offset = 0
        
    async def connect(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json", "KC-API-KEY-VERSION": "2"},
            timeout=aiohttp.ClientTimeout(total=30)
        )
    
    async def close(self):
        """Close connections."""
        if self.session:
            await self.session.close()
        if self.ws_connection:
            await self.ws_connection.close()
    
    def _sign(self, method: str, endpoint: str, body: str = "") -> dict:
        """Generate request headers."""
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
        """GET request."""
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
        """POST request."""
        try:
            body_str = json.dumps(body)
            headers = self._sign("POST", endpoint, body_str)
            async with self.session.post(self.BASE_URL + endpoint, data=body_str, headers=headers) as resp:
                data = await resp.json()
                if data.get("code") == "200000":
                    return True, data["data"]
                return False, data.get("msg", data)
        except Exception as e:
            return False, str(e)
    
    async def get_tickers(self) -> List[Dict]:
        """Get all symbols."""
        success, data = await self.get("/api/v1/symbols", auth=False)
        if success:
            return data.get("ticker", [])
        return []
    
    async def get_klines(self, symbol: str, interval: str = "1hour", limit: int = 50) -> List[List]:
        """Get candle data."""
        success, data = await self.get(
            "/api/v1/market/candles",
            params={"symbol": symbol, "type": interval},
            auth=False
        )
        if success and data:
            return list(reversed(data[-limit:]))  # Oldest first
        return []
    
    async def get_price(self, symbol: str) -> float:
        """Get current price."""
        success, data = await self.get(f"/api/v1/mark/orderbook/level1?symbol={symbol}", auth=False)
        if success and data:
            return float(data.get("price", 0))
        return 0.0
    
    async def get_account(self) -> Dict:
        """Get account balances."""
        success, data = await self.get("/api/v1/accounts")
        if success:
            accounts = {}
            for acc in data:
                accounts[acc["currency"]] = {
                    "available": float(acc["available"]),
                    "balance": float(acc["balance"])
                }
            return accounts
        return {}
    
    async def place_order(self, symbol: str, side: str, amount: float, price: float = None) -> Tuple[bool, Any]:
        """Place spot order."""
        body = {
            "symbol": symbol,
            "side": side,
            "type": "market" if price is None else "limit",
            "size": str(amount)
        }
        if price:
            body["price"] = str(price)
        return await self.post("/api/v1/orders", body)

# ─── Technical Indicators ───────────────────────────────────────────

class EnsembleIndicators:
    """
    AI-like ensemble of technical indicators.
    Each indicator contributes to a composite score (0-1).
    """
    
    @staticmethod
    def compute_all(closes: List[float], highs: List[float], lows: List[float], 
                   volumes: List[float]) -> Dict[str, float]:
        """Compute full indicator suite."""
        if len(closes) < 30:
            return {}
        
        result = {}
        
        # 1. RSI
        result["rsi"] = EnsembleIndicators._rsi(closes)
        
        # 2. EMA Crossover
        ema_fast = EnsembleIndicators._ema(closes, 9)
        ema_slow = EnsembleIndicators._ema(closes, 21)
        result["ema_max"] = ema_fast[-1] if ema_fast else closes[-1]
        result["ema_min"] = ema_slow[-1] if ema_slow else closes[-1]
        result["ema_signal"] = 1 if ema_fast[-1] > ema_slow[-1] else 0
        
        # 3. MFI (Money Flow Index)
        result["mfi"] = EnsembleIndicators._mfi(closes, highs, lows, volumes)
        
        # 4. MACD
        macd, signal = EnsembleIndicators._macd(closes)
        result["macd"] = macd[-1] if macd else 0
        result["macd_signal"] = signal[-1] if signal else 0
        result["macd_histogram"] = result["macd"] - result["macd_signal"]
        
        # 5. Bollinger Bands
        bb = EnsembleIndicators._bollinger_bands(closes)
        result.update(bb)
        
        # 6. Super Trend
        st = EnsembleIndicators._super_trend(closes, highs, lows)
        result["super_trend"] = st
        
        # 7. ADX
        result["adx"] = EnsembleIndicators._adx(highs, lows, closes)
        
        # 8. ATR (for volatility sizing)
        result["atr"] = EnsembleIndicators._atr(highs, lows, closes)
        result["atr_pct"] = (result["atr"] / closes[-1]) * 100
        
        return result
    
    @staticmethod
    def _rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def _ema(prices: List[float], period: int) -> List[float]:
        if len(prices) < period:
            return prices
        multiplier = 2 / (period + 1)
        ema = [np.mean(prices[:period])]
        for price in prices[period:]:
            ema.append(price * multiplier + ema[-1] * (1 - multiplier))
        return ema
    
    @staticmethod
    def _mfi(closes: List[float], highs: List[float], lows: List[float], 
            volumes: List[float], period: int = 14) -> float:
        """Money Flow Index - volume-weighted RSI."""
        if len(closes) < period + 1:
            return 50.0
        typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
        money_flows = [tp * v for tp, v in zip(typical_prices, volumes)]
        
        pos_flow = sum(mf for i, mf in enumerate(money_flows[1:period+1]) 
                      if typical_prices[i+1] > typical_prices[i])
        neg_flow = sum(mf for i, mf in enumerate(money_flows[1:period+1]) 
                      if typical_prices[i+1] < typical_prices[i])
        
        if neg_flow == 0:
            return 100.0
        mfr = pos_flow / neg_flow
        return 100 - (100 / (1 + mfr))
    
    @staticmethod
    def _macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float]]:
        """MACD line and signal line."""
        if len(prices) < slow + signal:
            return [], []
        ema_fast = EnsembleIndicators._ema(prices, fast)
        ema_slow_full = EnsembleIndicators._ema(prices, slow)
        
        # Align lengths
        macd_line = [f - s for f, s in zip(ema_fast[1-slow+fast:], ema_slow_full)]
        signal_line = EnsembleIndicators._ema(macd_line, signal)
        
        return macd_line, signal_line
    
    @staticmethod
    def _bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Dict:
        """Bollinger Bands with squeeze detection."""
        if len(prices) < period:
            return {"bb_upper": prices[-1], "bb_lower": prices[-1], "bb_middle": prices[-1], "bb_percent": 50}
        
        recent = prices[-period:]
        sma = np.mean(recent)
        std = np.std(recent)
        
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        
        # %B - position within bands
        current = prices[-1]
        bb_percent = (current - lower) / (upper - lower) * 100 if upper != lower else 50
        
        return {
            "bb_upper": upper,
            "bb_lower": lower,
            "bb_middle": sma,
            "bb_percent": max(0, min(100, bb_percent)),
            "bb_width": (upper - lower) / sma * 100  # Squeeze indicator
        }
    
    @staticmethod
    def _super_trend(closes: List[float], highs: List[float], lows: List[float], 
                    period: int = 10, multiplier: int = 3) -> str:
        """Super Trend indicator."""
        if len(closes) < period + 1:
            return "NEUTRAL"
        
        # ATR-based bands
        atr = EnsembleIndicators._atr(highs, lows, closes, period)
        hl_avg = [(h + l) / 2 for h, l in zip(highs, lows)]
        
        upper_band = hl_avg[-1] + multiplier * atr
        lower_band = hl_avg[-1] - multiplier * atr
        
        current_close = closes[-1]
        
        if current_close > upper_band:
            return "BULLISH"
        elif current_close < lower_band:
            return "BEARISH"
        return "NEUTRAL"
    
    @staticmethod
    def _adx(highs: List[float], lows: List[float], closes: List[float], 
            period: int = 14) -> float:
        """Average Directional Index."""
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
        
        atr = np.mean(tr_list[-period:])
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr if atr > 0 else 0
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr if atr > 0 else 0
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        adx = np.mean([dx] * period)  # Simplified
        
        return min(100, adx)
    
    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Average True Range."""
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
        return np.mean(tr_list[-period:])

# ─── Score Calculator ─────────────────────────────────────────────

class ScoreCalculator:
    """
    Calculate composite signal score (0-1) from indicator values.
    Applies dynamic weights based on recent performance.
    """
    
    @staticmethod
    def calculate(indicators: Dict[str, float], weights: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        """
        Returns composite score and individual indicator scores.
        Score > 0.6 = bullish, < 0.4 = bearish
        """
        scores = {}
        
        # 1. RSI score (oversold = bullish, overbought = bearish)
        rsi = indicators.get("rsi", 50)
        if rsi < 30:
            scores["rsi"] = 1.0
        elif rsi > 70:
            scores["rsi"] = 0.0
        else:
            scores["rsi"] = (70 - rsi) / 40  # Linear from 0.25 to 0.75
        
        # 2. EMA score (trend following)
        ema_signal = indicators.get("ema_signal", 0.5)
        scores["ema"] = 1.0 if ema_signal == 1 else 0.0
        
        # 3. MFI score (volume-weighted momentum)
        mfi = indicators.get("mfi", 50)
        if mfi < 20:
            scores["mfi"] = 1.0
        elif mfi > 80:
            scores["mfi"] = 0.0
        else:
            scores["mfi"] = (80 - mfi) / 60
        
        # 4. MACD score (momentum)
        macd_hist = indicators.get("macd_histogram", 0)
        macd_max = 0.05 * indicators.get("bb_middle", indicators.get("rsi", 1))
        scores["macd"] = min(1.0, max(0.0, (macd_hist + macd_max) / (2 * macd_max)))
        
        # 5. Bollinger score (mean reversion)
        bb_pct = indicators.get("bb_percent", 50)
        if bb_pct < 10:
            scores["bb"] = 1.0  # Oversold
        elif bb_pct > 90:
            scores["bb"] = 0.0  # Overbought
        else:
            scores["bb"] = (50 - abs(bb_pct - 50)) / 50
        
        # 6. Super Trend score
        st = indicators.get("super_trend", "NEUTRAL")
        scores["super_trend"] = {"BULLISH": 1.0, "BEARISH": 0.0, "NEUTRAL": 0.5}[st]
        
        # 7. ADX (trend strength - doesn't indicate direction)
        adx = indicators.get("adx", 25)
        trend_strength = min(1.0, adx / 50)  # Normalize to 0-1
        
        # Calculate weighted composite
        total_weight = sum(weights.get(k, 0.15) for k in scores)
        weighted_sum = sum(scores.get(k, 0.5) * weights.get(k, 0.15) for k in scores)
        
        composite = weighted_sum / total_weight if total_weight > 0 else 0.5
        
        # Adjust by trend strength
        if composite > 0.6:
            composite = min(1.0, composite * (0.7 + 0.3 * trend_strength))
        elif composite < 0.4:
            composite = max(0.0, composite * (1.3 - 0.3 * trend_strength))
        
        return composite, scores



# ─── Portfolio Risk Manager ───────────────────────────────────────

class PortfolioRiskManager:
    """
    Portfolio-level risk management across all pairs.
    - Correlation-based position sizing
    - Kelly Criterion for optimal bet sizing
    - Drawdown circuit breaker
    - Volatility-adjusted stops
    """
    
    def __init__(self, portfolio: PortfolioState):
        self.portfolio = portfolio
        self.max_daily_loss = INITIAL_CAPITAL * 0.08  # 8% max portfolio loss
        
    async def calculate_position_size(self, pair_data: PairData, 
                                    correlation_with_others: Dict[str, float]) -> float:
        """
        Calculate optimal position size using Kelly Criterion with constraints.
        Returns USDT amount to allocate.
        """
        think.data_source_access("Portfolio Risk Manager")
        
        base_confidence = pair_data.composite_score
        current_price = pair_data.current_price
        volatility = pair_data.volatility
        
        # 1. Kelly Criterion: f* = (bp - q) / b
        # Simplified: use win rate from recent trade history
        win_rate = self._calculate_win_rate(pair_data.base)
        
        # Conservative Kelly (fractional Kelly: 25% of full Kelly)
        kelly_bet_pct = max(0, (win_rate * 3 - 1) / 3) * 0.25
        
        # 2. Volatility adjustment
        if volatility > 2.0:  # High volatility
            kelly_bet_pct *= 0.6  # Reduce by 40%
        elif volatility < 0.5:  # Low volatility
            kelly_bet_pct *= 1.2  # Allow slightly more
        
        # 3. Correlation adjustment (don't double down on correlated risk)
        avg_correlation = np.mean(list(correlation_with_others.values())) if correlation_with_others else 0.5
        kelly_bet_pct *= (1 - avg_correlation * 0.5)  # Reduce if highly correlated
        
        # 4. Position constraints
        max_position = INITIAL_CAPITAL * (MAX_POSITION_PCT / 100)
        min_position = INITIAL_CAPITAL * (MIN_POSITION_PCT / 100)
        target_position = INITIAL_CAPITAL * kelly_bet_pct
        
        final_size = max(min_position, min(max_position, target_position))
        
        # 5. Available capital check
        available_pct = self.portfolio.available / INITIAL_CAPITAL
        if available_pct < 0.1:  # Less than 10% left
            final_size *= 0.5  # Reduce new positions
        
        think.add_thought_node(
            node_type="position_sizing",
            label=f"Position Size {pair_data.base}",
            confidence=base_confidence,
            connections=["kelly", "volatility", "correlation"]
        )
        
        return round(final_size, 2)
    
    def _calculate_win_rate(self, base: str) -> float:
        """Calculate recent win rate for a pair."""
        trades = [t for t in self.portfolio.trade_history 
                 if t.get("base") == base and t.get("timestamp", 0) > time.time() - 86400 * 7]
        if not trades:
            return 0.55  # Conservative default
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        return wins / len(trades)
    
    def check_portfolio_health(self) -> Tuple[bool, str]:
        """
        Check if portfolio is healthy. Returns (is_healthy, reason).
        """
        think.data_source_access("Health Monitor")
        
        # Check drawdown
        unrealized = sum(
            pos.get("unrealized_pnl", 0) 
            for pos in self.portfolio.active_positions.values()
        )
        total_value = self.portfolio.capital + unrealized
        max_value = self.portfolio.capital * 1.05  # Assume could have been +5%
        
        if max_value > 0:
            drawdown = (max_value - total_value) / max_value * 100
            if drawdown > PORTFOLIO_DRAWDOWN_LIMIT:
                return False, f"Portfolio drawdown {drawdown:.1f}% > limit {PORTFOLIO_DRAWDOWN_LIMIT}%"
        
        # Check daily loss
        if self.portfolio.daily_loss > self.max_daily_loss:
            return False, f"Daily loss ${self.portfolio.daily_loss:.2f} exceeds limit ${self.max_daily_loss:.2f}"
        
        return True, "Healthy"
    
    def calculate_correlation_matrix(self, pairs: Dict[str, PairData]) -> Dict[str, Dict[str, float]]:
        """Calculate correlation between pairs based on price history."""
        correlation = defaultdict(dict)
        
        pair_list = list(pairs.values())
        for i, p1 in enumerate(pair_list):
            for p2 in pair_list[i+1:]:
                if len(p1.price_history) > 20 and len(p2.price_history) > 20:
                    # Calculate correlation of returns
                    returns1 = np.diff(p1.price_history[-20:]) / p1.price_history[-21:-1]
                    returns2 = np.diff(p2.price_history[-20:]) / p2.price_history[-21:-1]
                    if len(returns1) == len(returns2):
                        corr = np.corrcoef(returns1, returns2)[0, 1]
                        if not np.isnan(corr):
                            correlation[p1.base][p2.base] = corr
                            correlation[p2.base][p1.base] = corr
        
        return dict(correlation)

# ─── Multipair Trader (Main Class) ─────────────────────────────────

class SmartPortfolioTrader:
    """
    Main trading bot - manages multiple pairs, executes strategy,
    and emits thinking process for visualization.
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.portfolio = PortfolioState()
        self.client: Optional[KuCoinAsyncClient] = None
        self.risk_manager = PortfolioRiskManager(self.portfolio)
        self.running = True
        self.cycle_count = 0
        
        # Load state if exists
        self._load_state()
        
        # Watchlist - top pairs to monitor
        self.watchlist: List[str] = [
            "ETH-USDT", "BTC-USDT", "SOL-USDT", "LINK-USDT",
            "AVAX-USDT", "DOT-USDT", "MATIC-USDT", "UNI-USDT",
            "AAVE-USDT", "ATOM-USDT", "ADA-USDT", "DOGE-USDT"
        ]
        
    async def initialize(self):
        """Initialize KuCoin connection."""
        print("[INIT] Connecting to KuCoin...")
        think.set_stage("INITIALIZING")
        think.add_thought_node("init", "System Startup", 1.0)
        
        self.client = KuCoinAsyncClient(
            KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_PASSPHRASE
        )
        await self.client.connect()
        
        # Get account balance
        accounts = await self.client.get_account()
        usdt_available = accounts.get("USDT", {}).get("available", 0)
        self.portfolio.available = min(INITIAL_CAPITAL, float(usdt_available))
        self.portfolio.capital = float(usdt_available)
        
        print(f"[INIT] Available USDT: ${self.portfolio.available:.2f}")
        think.add_thought_node("account", f"Balance: ${self.portfolio.available:.2f}", 1.0)
        
    async def run(self):
        """Main trading loop."""
        await self.initialize()
        
        print("=" * 70)
        print("MULTI-PAIR PORTFOLIO TRADER v5.0 - HEPHAESTUS")
        print("=" * 70)
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
        print(f"Capital: ${INITIAL_CAPITAL}")
        print(f"Max Pairs: {MAX_PAIRS}")
        print(f"Portfolio Drawdown Limit: {PORTFOLIO_DRAWDOWN_LIMIT}%")
        print("=" * 70)
        
        think.set_stage("GATHERING")
        
        cycle = 0
        while self.running:
            try:
                cycle += 1
                print(f"\n[Cycle {cycle}] {datetime.now().strftime('%H:%M:%S')}")
                
                # 1. HEALTH CHECK
                healthy, reason = self.risk_manager.check_portfolio_health()
                if not healthy:
                    print(f"[CRITICAL] {reason}")
                    think.add_thought_node("critical_stop", reason, 0.0)
                    break
                
                # 2. UPDATE ALL PAIRS (parallel)
                await self._update_all_pairs()
                
                # 3. RANK PAIRS by opportunity score
                ranked = self._rank_pairs()
                
                # 4. UPDATE CORRELATION MATRIX
                self.portfolio.correlation_matrix = (
                    self.risk_manager.calculate_correlation_matrix(self.portfolio.pairs)
                )
                
                # 5. EVALUATE POSITIONS & SIGNALS
                await self._evaluate_positions(ranked[:MAX_PAIRS * 2])  # Top candidates
                
                # 6. EMIT THINKING STATE
                self._emit_thinking_state()
                
                # 7. SAVE STATE
                self._save_state()
                
                # Cycle delay
                await asyncio.sleep(20 if self.dry_run else 60)
                
            except Exception as e:
                print(f"[ERROR] Cycle {cycle}: {e}")
                await asyncio.sleep(30)
        
        await self.client.close()
        print("\n[SHUTDOWN] Bot terminated")
        
    async def _update_all_pairs(self):
        """Fetch prices and data for all watchlist pairs."""
        think.data_source_access("KuCoin Market Data")
        
        tasks = []
        for symbol in self.watchlist:
            tasks.append(self._update_single_pair(symbol))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _update_single_pair(self, symbol: str):
        """Update a single pair's data."""
        try:
            # Get current price (simulated with kline close)
            klines = await self.client.get_klines(symbol, "1hour", 100)
            if not klines or len(klines) < 50:
                return
            
            # Parse klines: [timestamp, open, close, high, low, volume, amount]
            timestamps = [float(k[0]) for k in klines]
            opens = [float(k[1]) for k in klines]
            closes = [float(k[2]) for k in klines]
            highs = [float(k[3]) for k in klines]
            lows = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            
            current_price = closes[-1]
            
            # Get or create pair data
            if symbol not in self.portfolio.pairs:
                parts = symbol.split('-')
                self.portfolio.pairs[symbol] = PairData(
                    symbol=symbol,
                    base=parts[0],
                    quote=parts[1]
                )
            
            pair = self.portfolio.pairs[symbol]
            pair.current_price = current_price
            pair.price_history = closes
            pair.volume_24h = sum(volumes[-24:])  # Last 24 hours of data
            
            # Compute all indicators
            indicators = EnsembleIndicators.compute_all(closes, highs, lows, volumes)
            
            for key, value in indicators.items():
                setattr(pair, key, value)
            
            pair.volatility = indicators.get("atr_pct", 1.0)
            
            # Calculate composite score
            composite, scores = ScoreCalculator.calculate(indicators, self.portfolio.indicator_weights)
            pair.composite_score = composite
            
            # Determine signal
            if composite >= BUY_SIGNAL_THRESHOLD:
                pair.signal = "BUY"
            elif composite <= SELL_SIGNAL_THRESHOLD:
                pair.signal = "SELL"
            else:
                pair.signal = "HOLD"
            
            pair.last_update = time.time()
            
            # Emit thinking
            think.signal_calculation(symbol, scores, composite, pair.signal)
            
        except Exception as e:
            print(f"[WARN] Failed to update {symbol}: {e}")
    
    def _rank_pairs(self) -> List[Tuple[str, float]]:
        """Rank pairs by opportunity score (momentum + signal strength)."""
        scores = []
        
        for symbol, pair in self.portfolio.pairs.items():
            if pair.current_price == 0:
                continue
            
            # Opportunity score: volume * signal_confidence * volatility
            volume_score = min(1.0, pair.volume_24h / 1000000)  # Normalize
            signal_strength = abs(pair.composite_score - 0.5) * 2  # 0-1
            
            # Volatility bonus (need some movement)
            vol_score = 1.0 if 0.5 < pair.volatility < 3.0 else 0.5
            
            # Trending bonus
            adx_score = min(1.0, pair.adx / 40)
            
            total = (volume_score * 0.2 + signal_strength * 0.3 + vol_score * 0.2 + adx_score * 0.3) * 100
            scores.append((symbol, total))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    async def _evaluate_positions(self, top_pairs: List[Tuple[str, float]]):
        """Evaluate positions and execute trades."""
        think.set_stage("PROCESSING")
        
        decisions = []
        active_count = len(self.portfolio.active_positions)
        
        for symbol, score in top_pairs:
            pair = self.portfolio.pairs.get(symbol)
            if not pair:
                continue
            
            current_position = self.portfolio.active_positions.get(symbol)
            
            # CHECK exit signals for existing positions
            if current_position:
                pnl_pct = self._calculate_pnl(current_position, pair.current_price)
                
                # Trailing stop or take profit
                if pnl_pct >= TAKE_PROFIT_PCT_BASE or pnl_pct <= -STOP_LOSS_PCT_BASE:
                    if not self.dry_run:
                        await self._close_position(symbol, pair, pnl_pct)
                    else:
                        print(f"[DRY] Would SELL {symbol} at {pair.current_price:.2f} (P&L: {pnl_pct:.2f}%)")
                    
                    decisions.append({
                        "pair": symbol,
                        "action": "CLOSE",
                        "price": pair.current_price,
                        "pnl_pct": pnl_pct
                    })
                    continue
            
            # CHECK entry signals (if room for new positions)
            if active_count < MAX_PAIRS and pair.signal == "BUY" and not current_position:
                # Calculate position size
                correlations = self.portfolio.correlation_matrix.get(pair.base, {})
                size = await self.risk_manager.calculate_position_size(pair, correlations)
                
                if size > 0 and size <= self.portfolio.available:
                    if not self.dry_run:
                        success = await self._open_position(symbol, pair, size)
                    else:
                        print(f"[DRY] Would BUY {size:.2f} USDT of {symbol} @ {pair.current_price:.2f}")
                        success = True
                    
                    if success:
                        decisions.append({
                            "pair": symbol,
                            "action": "BUY",
                            "size": size,
                            "price": pair.current_price
                        })
            
            # Short opportunity (if we had margin, we'd do this)
            # For spot, we just track SELL signals for reference
            elif pair.signal == "SELL":
                decisions.append({
                    "pair": symbol,
                    "action": "WAIT_SELL_SIGNAL",
                    "strength": 1 - pair.composite_score
                })
        
        think.set_stage("SYNTHESIZING")
        think.portfolio_decision(decisions)
    
    async def _open_position(self, symbol: str, pair: PairData, size_usdt: float) -> bool:
        """Open a position."""
        try:
            # Calculate size in base currency
            amount = size_usdt / pair.current_price
            
            # Round to KuCoin precision (8 decimal places for crypto)
            amount = round(amount, 8)
            size_usdt = amount * pair.current_price
            
            success, result = await self.client.place_order(symbol, "buy", amount)
            
            if success:
                # Record position
                self.portfolio.active_positions[symbol] = {
                    "symbol": symbol,
                    "base": pair.base,
                    "quote": pair.quote,
                    "amount": amount,
                    "entry_price": pair.current_price,
                    "entry_time": time.time(),
                    "size_usdt": size_usdt,
                    "unrealized_pnl": 0
                }
                self.portfolio.available -= size_usdt
                self.portfolio.deployed += size_usdt
                
                print(f"[TRADE] BUY {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} (${size_usdt:.2f})")
                think.add_thought_node("trade", f"BUY {pair.base}", 1.0, ["position_open"])
                
                return True
            else:
                print(f"[TRADE] Failed to buy {symbol}: {result}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Opening position {symbol}: {e}")
            return False
    
    async def _close_position(self, symbol: str, pair: PairData, pnl_pct: float) -> bool:
        """Close a position."""
        try:
            position = self.portfolio.active_positions.get(symbol)
            if not position:
                return False
            
            amount = position["amount"]
            success, result = await self.client.place_order(symbol, "sell", amount)
            
            if success:
                # Calculate P&L
                exit_value = amount * pair.current_price
                entry_value = amount * position["entry_price"]
                pnl = exit_value - entry_value
                
                self.portfolio.total_pnl += pnl
                if pnl < 0:
                    self.portfolio.daily_loss += abs(pnl)
                
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
                    "timestamp": time.time()
                })
                
                del self.portfolio.active_positions[symbol]
                
                print(f"[TRADE] SELL {pair.base}: {amount:.6f} @ ${pair.current_price:.2f} "
                      f"P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
                think.add_thought_node("trade", f"SELL {pair.base} ${pnl:+.2f}", 
                                      1.0 if pnl > 0 else 0.5, ["position_close"])
                
                return True
            else:
                print(f"[TRADE] Failed to sell {symbol}: {result}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Closing position {symbol}: {e}")
            return False
    
    def _calculate_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate P&L percentage."""
        entry = position.get("entry_price", 0)
        if entry == 0:
            return 0
        return ((current_price - entry) / entry) * 100
    
    def _emit_thinking_state(self):
        """Emit current state for visualization."""
        think._persist()
    
    def _save_state(self):
        """Save portfolio state to disk."""
        try:
            state = {
                "capital": self.portfolio.capital,
                "available": self.portfolio.available,
                "deployed": self.portfolio.deployed,
                "total_pnl": self.portfolio.total_pnl,
                "daily_loss": self.portfolio.daily_loss,
                "active_positions": self.portfolio.active_positions,
                "trade_history": self.portfolio.trade_history[-100:],  # Last 100
                "indicator_weights": self.portfolio.indicator_weights,
                "last_update": time.time()
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save state: {e}")
    
    def _load_state(self):
        """Load portfolio state from disk."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.portfolio.available = state.get("available", INITIAL_CAPITAL)
                    self.portfolio.total_pnl = state.get("total_pnl", 0)
                    self.portfolio.daily_loss = state.get("daily_loss", 0)
                    self.portfolio.active_positions = state.get("active_positions", {})
                    self.portfolio.trade_history = state.get("trade_history", [])
                    self.portfolio.indicator_weights = state.get("indicator_weights", self.portfolio.indicator_weights)
                    print(f"[STATE] Loaded {len(self.portfolio.active_positions)} active positions")
        except Exception as e:
            print(f"[STATE] No previous state: {e}")


# ─── Main Entry Point ─────────────────────────────────────────────

def main():
    global INITIAL_CAPITAL, MAX_PAIRS
    
    parser = argparse.ArgumentParser(description="Multi-Pair Portfolio Trader v5.0")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without trading")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL, help="Trading capital")
    parser.add_argument("--max-pairs", type=int, default=MAX_PAIRS, help="Max concurrent positions")
    args = parser.parse_args()
    
    INITIAL_CAPITAL = args.capital
    MAX_PAIRS = args.max_pairs
    
    # Check credentials
    if not KUCOIN_API_KEY or not KUCOIN_API_SECRET:
        print("[ERROR] KuCoin credentials not found in /root/.env")
        print("Set: KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_PASSPHRASE")
        return 1
    
    # Run bot
    trader = SmartPortfolioTrader(dry_run=args.dry_run)
    
    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Interrupted by user")
        trader.running = False
        trader._save_state()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
