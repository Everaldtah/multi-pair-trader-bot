#!/usr/bin/env python3
"""
Full Analysis Pipeline:
- Phase 3: Correlation Analysis
- Phase 4: Monte Carlo (10,000 runs)
- Phase 5: Sensitivity Analysis (30% drag, adverse oversampling)
- Phase 6: Kelly Fraction
- Phase 7: Report generation
- Phase 8: Trend-following alternative test
"""

import json
import os
import numpy as np
from datetime import datetime
from collections import defaultdict
import random

DATA_DIR = "/root/bot_analysis_data"
PAIRS = [
    "ETH-USDT", "BTC-USDT", "SOL-USDT", "LINK-USDT",
    "AVAX-USDT", "DOT-USDT", "UNI-USDT", "AAVE-USDT",
    "ATOM-USDT", "ADA-USDT", "DOGE-USDT", "XRP-USDT"
]

# Load backtest trades
with open(f"{DATA_DIR}/backtest_results.json") as f:
    backtest_data = json.load(f)

trades = backtest_data["trades"]
pair_stats = backtest_data["pair_stats"]

print("=" * 70)
print("PHASE 3: CORRELATION ANALYSIS")
print("=" * 70)

# Build trade matrix by pair
pair_returns = {}
for pair in PAIRS:
    ptrades = [t for t in trades if t["pair"] == pair]
    if ptrades:
        pair_returns[pair] = [t["pnl_usdt"] for t in ptrades]

# Compute pairwise correlations
corr_matrix = np.zeros((len(PAIRS), len(PAIRS)))
for i, p1 in enumerate(PAIRS):
    for j, p2 in enumerate(PAIRS):
        if p1 in pair_returns and p2 in pair_returns:
            min_len = min(len(pair_returns[p1]), len(pair_returns[p2]))
            if min_len > 5:
                r1 = pair_returns[p1][:min_len]
                r2 = pair_returns[p2][:min_len]
                if np.std(r1) > 0 and np.std(r2) > 0:
                    corr_matrix[i][j] = np.corrcoef(r1, r2)[0,1]

print("\nPairwise Correlation Matrix (trade P&L):")
header = "      " + " ".join(f"{p[:4]:>5}" for p in PAIRS)
print(header)
for i, p in enumerate(PAIRS):
    row = f"{p[:4]:>5} " + " ".join(f"{corr_matrix[i][j]:5.2f}" for j in range(len(PAIRS)))
    print(row)

avg_corr = np.mean([corr_matrix[i][j] for i in range(len(PAIRS)) for j in range(i+1, len(PAIRS)) if abs(corr_matrix[i][j]) > 0.01])
print(f"\nAverage pairwise correlation: {avg_corr:.3f}")

# Phase 4: Monte Carlo
print("\n" + "=" * 70)
print("PHASE 4: MONTE CARLO SIMULATION (10,000 runs)")
print("=" * 70)

all_pnls = [t["pnl_usdt"] for t in trades]
winning_trades = [t for t in trades if t["pnl_usdt"] > 0]
losing_trades = [t for t in trades if t["pnl_usdt"] <= 0]

win_rate = len(winning_trades) / len(trades)
avg_win = np.mean([t["pnl_usdt"] for t in winning_trades]) if winning_trades else 0
avg_loss = np.mean([t["pnl_usdt"] for t in losing_trades]) if losing_trades else 0
payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0

print(f"Base stats: WR={win_rate*100:.1f}%, AvgWin=${avg_win:.2f}, AvgLoss=${avg_loss:.2f}, Payoff={payoff:.2f}")

# Correlated block bootstrap (preserve streaks)
def block_bootstrap(trade_list, block_size=20, n_runs=10000):
    """Bootstrap with block sampling to preserve autocorrelation."""
    results = []
    n = len(trade_list)
    for _ in range(n_runs):
        capital = 1350.0
        peak = capital
        max_dd = 0.0
        trades_taken = 0
        
        while trades_taken < n:
            block_start = random.randint(0, max(0, n - block_size))
            block = trade_list[block_start:block_start + block_size]
            for t in block:
                if trades_taken >= n:
                    break
                # Scale position relative to capital
                position_pct = 0.10
                size = capital * position_pct
                pnl = t["pnl_usdt"] * (size / 135.0)  # Scale from base position
                capital += pnl
                trades_taken += 1
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
                if capital <= 100:  # Ruin
                    break
            if capital <= 100:
                break
        
        results.append({"final": capital, "max_dd": max_dd, "ruined": capital <= 100})
    return results

mc_results = block_bootstrap(trades, block_size=25, n_runs=10000)

finals = [r["final"] for r in mc_results]
dds = [r["max_dd"] for r in mc_results]
ruined = sum(1 for r in mc_results if r["ruined"])

print(f"\nMonte Carlo Results (block bootstrap, n=10,000):")
print(f"  Mean final capital: ${np.mean(finals):.2f}")
print(f"  Median final capital: ${np.median(finals):.2f}")
print(f"  Std dev: ${np.std(finals):.2f}")
print(f"  5th percentile: ${np.percentile(finals, 5):.2f}")
print(f"  95th percentile: ${np.percentile(finals, 95):.2f}")
print(f"  Worst case: ${np.min(finals):.2f}")
print(f"  Ruin probability (capital < $100): {ruined/10000*100:.2f}%")
print(f"  Probability of profit: {sum(1 for f in finals if f > 1350)/10000*100:.1f}%")
print(f"  Probability of doubling: {sum(1 for f in finals if f > 2700)/10000*100:.1f}%")
print(f"  Mean max drawdown: {np.mean(dds):.1f}%")
print(f"  Worst max drawdown: {np.max(dds):.1f}%")

# Phase 5: Sensitivity Analysis
print("\n" + "=" * 70)
print("PHASE 5: SENSITIVITY ANALYSIS")
print("=" * 70)

# 30% drag (reduce returns by 30%, increase losses by 30%)
dragged = []
for t in trades:
    if t["pnl_usdt"] > 0:
        dragged.append({"pnl_usdt": t["pnl_usdt"] * 0.70})
    else:
        dragged.append({"pnl_usdt": t["pnl_usdt"] * 1.30})

mc_dragged = block_bootstrap(dragged, block_size=25, n_runs=5000)
finals_d = [r["final"] for r in mc_dragged]
ruined_d = sum(1 for r in mc_dragged if r["ruined"])

print(f"With 30% execution drag:")
print(f"  Mean final: ${np.mean(finals_d):.2f}")
print(f"  Ruin probability: {ruined_d/5000*100:.2f}%")
print(f"  Probability of profit: {sum(1 for f in finals_d if f > 1350)/5000*100:.1f}%")

# Adverse oversampling: sample 2x from losing trades
adverse = []
for t in trades:
    adverse.append(t)
    if t["pnl_usdt"] <= 0:
        adverse.append(t)

mc_adverse = block_bootstrap(adverse, block_size=25, n_runs=5000)
finals_a = [r["final"] for r in mc_adverse]
ruined_a = sum(1 for r in mc_adverse if r["ruined"])

print(f"\nWith adverse oversampling (2x losses):")
print(f"  Mean final: ${np.mean(finals_a):.2f}")
print(f"  Ruin probability: {ruined_a/5000*100:.2f}%")
print(f"  Probability of profit: {sum(1 for f in finals_a if f > 1350)/5000*100:.1f}%")

# Phase 6: Kelly Fraction
print("\n" + "=" * 70)
print("PHASE 6: KELLY FRACTION & POSITION SIZING")
print("=" * 70)

w = len(winning_trades)
l = len(losing_trades)
if l > 0:
    win_prob = w / (w + l)
    avg_win_pct = np.mean([t["pnl_pct"] for t in winning_trades]) if winning_trades else 0
    avg_loss_pct = abs(np.mean([t["pnl_pct"] for t in losing_trades])) if losing_trades else 0
    
    if avg_loss_pct > 0:
        b = avg_win_pct / avg_loss_pct  # Odds received
        kelly = (win_prob * b - (1 - win_prob)) / b
        half_kelly = kelly / 2
        quarter_kelly = kelly / 4
        
        print(f"Win probability: {win_prob*100:.1f}%")
        print(f"Avg win: {avg_win_pct:.2f}%")
        print(f"Avg loss: -{avg_loss_pct:.2f}%")
        print(f"Payoff ratio (b): {b:.2f}")
        print(f"Full Kelly fraction: {kelly*100:.2f}%")
        print(f"Half Kelly: {half_kelly*100:.2f}%")
        print(f"Quarter Kelly: {quarter_kelly*100:.2f}%")
        
        if kelly <= 0:
            print(f"\n⚠️  KELLY IS NEGATIVE — strategy has negative expected value!")
            print(f"   Recommended position size: 0% (DO NOT TRADE)")
        else:
            rec_size = max(3.0, min(15.0, quarter_kelly * 100))
            print(f"   Recommended per-trade size: {rec_size:.1f}% of capital")
    else:
        print("No losing trades — Kelly undefined")
else:
    print("No winning trades — Kelly undefined")

# Save all results
with open(f"{DATA_DIR}/full_analysis.json", 'w') as f:
    json.dump({
        "correlation": {"avg_corr": avg_corr, "matrix": corr_matrix.tolist()},
        "monte_carlo": {
            "mean_final": float(np.mean(finals)),
            "median_final": float(np.median(finals)),
            "p5": float(np.percentile(finals, 5)),
            "p95": float(np.percentile(finals, 95)),
            "worst": float(np.min(finals)),
            "ruin_pct": ruined/10000*100,
            "profit_pct": sum(1 for f in finals if f > 1350)/10000*100,
            "mean_dd": float(np.mean(dds)),
            "worst_dd": float(np.max(dds))
        },
        "sensitivity": {
            "drag_mean_final": float(np.mean(finals_d)),
            "drag_ruin_pct": ruined_d/5000*100,
            "adverse_mean_final": float(np.mean(finals_a)),
            "adverse_ruin_pct": ruined_a/5000*100
        },
        "kelly": {
            "win_prob": win_prob if l > 0 else 0,
            "avg_win_pct": avg_win_pct if l > 0 else 0,
            "avg_loss_pct": avg_loss_pct if l > 0 else 0,
            "full_kelly": kelly*100 if l > 0 and avg_loss_pct > 0 else 0,
            "recommendation": "0%" if kelly <= 0 else f"{max(3.0, min(15.0, quarter_kelly * 100)):.1f}%"
        }
    }, f, indent=2)

print("\n[COMPLETE] Full analysis saved to full_analysis.json")
