#!/usr/bin/env python3
"""
Multi-Pair Bot Performance Report Generator
===========================================

Run manually to get full trading performance report.
Parses bot logs and generates comprehensive statistics.

Usage:
    python3 multi_bot_report.py
"""

import re
import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "dry_run_bot.log"
STATE_FILE = Path(__file__).parent / "multi_bot_monitor_state.json"
INITIAL_CAPITAL = 500.00

def generate_report():
    """Generate comprehensive trading report"""
    print("=" * 60)
    print("📊 MULTI-PAIR BOT PERFORMANCE REPORT")
    print("=" * 60)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    
    # Load state
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "last_cycle": 0,
            "closed_trades": [],
            "highest_balance": INITIAL_CAPITAL,
            "total_profit_loss": 0.0
        }
    
    # Parse current log
    if LOG_FILE.exists():
        with open(LOG_FILE, 'r') as f:
            content = f.read()
        
        # Get latest cycle
        cycle_match = re.findall(r'CYCLE\s+(\d+)', content)
        current_cycle = int(cycle_match[-1]) if cycle_match else 0
        
        # Get latest portfolio
        summary_pattern = r'Portfolio Summary:\s+Open Positions:\s+(\d+).*?Available Cash:\s+£([\d.]+).*?Total P&L:\s+£([\d.-]+).*?Total Value:\s+£([\d.]+)'
        summaries = re.findall(summary_pattern, content, re.DOTALL)
        
        if summaries:
            latest = summaries[-1]
            positions_open = int(latest[0])
            available = float(latest[1])
            total_pnl = float(latest[2])
            total_value = float(latest[3])
            
            print("💰 CURRENT PORTFOLIO STATUS")
            print("-" * 60)
            print(f"  Total Value:      £{total_value:.2f}")
            print(f"  Available Cash:   £{available:.2f}")
            print(f"  Invested:         £{total_value - available:.2f}")
            print(f"  Total P&L:        £{total_pnl:+.2f} ({(total_pnl/INITIAL_CAPITAL)*100:+.2f}%)")
            print(f"  Open Positions:   {positions_open}/5")
            print()
            
            # Check against initial capital
            if total_value > INITIAL_CAPITAL:
                profit = total_value - INITIAL_CAPITAL
                print(f"  🎉 ABOVE INITIAL CAPITAL! Profit: £{profit:.2f}")
            elif total_value < INITIAL_CAPITAL:
                loss = INITIAL_CAPITAL - total_value
                print(f"  ⚠️  Below initial capital. Down: £{loss:.2f}")
            else:
                print(f"  ⚪ At breakeven with initial capital")
            print()
        
        # Get open positions with P&L
        position_pattern = r'📊\s+(\w+-USDT):\s+\$([\d.]+)\s+\|\s+P&L:\s+([+-]?[\d.]+%)'
        all_positions = re.findall(position_pattern, content)
        
        if all_positions:
            # Get unique latest positions
            latest_positions = {}
            for pair, price, pnl in all_positions:
                latest_positions[pair] = {"price": price, "pnl": pnl}
            
            print("📈 OPEN POSITIONS")
            print("-" * 60)
            for pair, data in latest_positions.items():
                pnl_float = float(data['pnl'].replace('%', ''))
                emoji = "🟢" if pnl_float > 0 else "🔴" if pnl_float < 0 else "⚪"
                print(f"  {emoji} {pair}: ${data['price']} | P&L: {data['pnl']}")
            print()
        
        # Parse all buy/sell activity
        buy_pattern = r'🟢\s+BUY\s+(\w+-USDT)\s+@\s+\$([\d.]+)'
        sell_pattern = r'🔴\s+SELL\s+(\w+-USDT)\s+@\s+\$([\d.]+)'
        
        all_buys = re.findall(buy_pattern, content)
        all_sells = re.findall(sell_pattern, content)
        
        print("📊 TRADE ACTIVITY")
        print("-" * 60)
        print(f"  Total Buy Signals:   {len(all_buys)}")
        print(f"  Total Sell Signals:  {len(all_sells)}")
        print(f"  Cycles Completed:    {current_cycle}")
        print()
        
        # Recent activity
        if all_buys or all_sells:
            print("🔄 RECENT ACTIVITY (last 10)")
            print("-" * 60)
            
            # Combine and sort
            activity = []
            for pair, price in all_buys:
                activity.append(("BUY", pair, price))
            for pair, price in all_sells:
                activity.append(("SELL", pair, price))
            
            for action, pair, price in activity[-10:]:
                emoji = "🟢" if action == "BUY" else "🔴"
                print(f"  {emoji} {action:4} {pair} @ ${price}")
            print()
    else:
        print("❌ No bot log file found")
        print()
    
    # Closed trades summary
    if state["closed_trades"]:
        print("🏆 CLOSED TRADES SUMMARY")
        print("-" * 60)
        wins = sum(1 for t in state["closed_trades"] 
                  if float(t['pnl_pct'].replace('%', '')) > 0)
        losses = len(state["closed_trades"]) - wins
        win_rate = (wins / len(state["closed_trades"])) * 100 if state["closed_trades"] else 0
        
        print(f"  Total Closed:  {len(state['closed_trades'])}")
        print(f"  Winning:       {wins} ({win_rate:.1f}%)")
        print(f"  Losing:        {losses}")
        print(f"  Total P&L:     £{state['total_profit_loss']:+.2f}")
        print()
        
        print("📜 RECENT CLOSED TRADES")
        print("-" * 60)
        for trade in state["closed_trades"][-5:]:
            pnl_float = float(trade['pnl_pct'].replace('%', ''))
            emoji = "🟢" if pnl_float > 0 else "🔴"
            print(f"  {emoji} {trade['pair']} @ ${trade['price']:.2f} | {trade['pnl_pct']}")
        print()
    
    # Overall stats
    print("📈 OVERALL STATISTICS")
    print("-" * 60)
    print(f"  Highest Balance:   £{state['highest_balance']:.2f}")
    print(f"  Initial Capital:   £{INITIAL_CAPITAL:.2f}")
    print(f"  Peak Performance:  £{state['highest_balance'] - INITIAL_CAPITAL:+.2f}")
    print()
    
    print("=" * 60)

if __name__ == "__main__":
    generate_report()
