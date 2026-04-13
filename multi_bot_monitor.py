#!/usr/bin/env python3
"""
Multi-Pair Bot Trade Monitor
============================

Tracks trade closures from bot logs and sends notifications
for profit milestones and completed trades.

Supports Telegram notifications (optional).

Usage:
    python3 multi_bot_monitor.py

Environment:
    TELEGRAM_TOKEN      - Bot token for Telegram notifications
    TELEGRAM_CHAT_ID    - Chat ID to send notifications to
"""

import re
import json
import os
from datetime import datetime
from pathlib import Path

# Config
LOG_FILE = Path(__file__).parent / "dry_run_bot.log"
STATE_FILE = Path(__file__).parent / "multi_bot_monitor_state.json"
INITIAL_CAPITAL = 500.00
NOTIFICATION_THRESHOLD = 500.00  # Notify when above this

# Telegram config from env
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_BOT_CHAT_ID", "")

def load_state():
    """Load monitor state"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "last_cycle": 0,
        "closed_trades": [],
        "highest_balance": INITIAL_CAPITAL,
        "notification_sent_above_threshold": False,
        "total_profit_loss": 0.0
    }

def save_state(state):
    """Save monitor state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def send_telegram_notification(message):
    """Send notification via Telegram bot if configured"""
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    
    if not token:
        print(f"[NOTIFICATION - No Telegram configured]\n{message}")
        return
    
    import urllib.request
    import urllib.parse
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Notification sent: {resp.status}")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def parse_log_file():
    """Parse the bot log for trade activity"""
    if not LOG_FILE.exists():
        return None, []
    
    with open(LOG_FILE, 'r') as f:
        content = f.read()
    
    # Find current cycle
    cycle_match = re.findall(r'CYCLE\s+(\d+)', content)
    current_cycle = int(cycle_match[-1]) if cycle_match else 0
    
    # Find portfolio summary blocks
    summary_pattern = r'Portfolio Summary:\s+Open Positions:\s+(\d+).*?Available Cash:\s+£([\d.]+).*?Total P&L:\s+£([\d.-]+).*?Total Value:\s+£([\d.]+)'
    summaries = re.findall(summary_pattern, content, re.DOTALL)
    
    # Find individual position P&L
    position_pattern = r'📊\s+(\w+-USDT):\s+\$([\d.]+)\s+\|\s+P&L:\s+([+-]?[\d.]+%)'
    positions = re.findall(position_pattern, content)
    
    # Find SELL signals (trade closures)
    sell_pattern = r'🔴\s+SELL\s+(\w+-USDT)\s+@\s+\$([\d.]+).*?P&L:\s+([+-]?[\d.]+%)'
    sells = re.findall(sell_pattern, content)
    
    # Find BUY signals
    buy_pattern = r'🟢\s+BUY\s+(\w+-USDT)\s+@\s+\$([\d.]+)'
    buys = re.findall(buy_pattern, content)
    
    return current_cycle, {
        "summaries": summaries,
        "positions": positions,
        "sells": sells,
        "buys": buys
    }

def check_and_notify():
    """Main monitoring function"""
    state = load_state()
    current_cycle, data = parse_log_file()
    
    if not current_cycle:
        print("No bot log data found")
        return
    
    if current_cycle <= state["last_cycle"]:
        print(f"No new cycles. Current: {current_cycle}, Last checked: {state['last_cycle']}")
        return
    
    print(f"Processing cycles {state['last_cycle'] + 1} to {current_cycle}")
    
    # Get latest summary
    total_value = None
    total_pnl = 0.0
    if data["summaries"]:
        latest = data["summaries"][-1]
        positions_open, available, total_pnl, total_value = latest
        positions_open = int(positions_open)
        available = float(available)
        total_pnl = float(total_pnl)
        total_value = float(total_value)
        
        print(f"Current Status: £{total_value:.2f} (P&L: £{total_pnl:+.2f})")
        
        # Check for new trade closures (sells)
        new_sells = []
        for sell in data["sells"]:
            pair, price, pnl_pct = sell
            sell_key = f"{pair}_{price}_{current_cycle}"
            if sell_key not in [s.get("key") for s in state["closed_trades"]]:
                new_sells.append({
                    "key": sell_key,
                    "pair": pair,
                    "price": float(price),
                    "pnl_pct": pnl_pct,
                    "cycle": current_cycle,
                    "time": datetime.now().isoformat()
                })
        
        # Send notifications for new closed trades
        for sell in new_sells:
            pnl_float = float(sell["pnl_pct"].replace('%', ''))
            emoji = "🟢 PROFIT" if pnl_float > 0 else "🔴 LOSS"
            
            message = f"""🎯 <b>MULTI-PAIR BOT: TRADE CLOSED</b>

{emoji}: {sell['pair']}
💰 Exit Price: ${sell['price']:.2f}
📊 P&L: {sell['pnl_pct']}
⏱️ Cycle: {sell['cycle']}

💼 Portfolio: £{total_value:.2f}
📈 Total P&L: £{total_pnl:+.2f}"""
            
            send_telegram_notification(message)
            state["closed_trades"].append(sell)
            print(f"Recorded closed trade: {sell['pair']} at {sell['pnl_pct']}")
        
        # Check if balance crossed above threshold
        if total_value > NOTIFICATION_THRESHOLD:
            if not state["notification_sent_above_threshold"]:
                profit = total_value - INITIAL_CAPITAL
                message = f"""🎉 <b>MULTI-PAIR BOT: PROFIT MILESTONE!</b>

💰 Balance: £{total_value:.2f}
📈 Above Initial: +£{profit:.2f}
🎯 Total P&L: £{total_pnl:+.2f}

✅ Initial capital of £{INITIAL_CAPITAL} has been exceeded!"""
                
                send_telegram_notification(message)
                state["notification_sent_above_threshold"] = True
                print(f"Milestone notification sent: £{total_value:.2f}")
        else:
            # Reset flag if balance drops back below
            if state["notification_sent_above_threshold"]:
                state["notification_sent_above_threshold"] = False
        
        # Track highest balance
        if total_value > state["highest_balance"]:
            state["highest_balance"] = total_value
            print(f"New highest balance: £{total_value:.2f}")
    
    state["last_cycle"] = current_cycle
    state["total_profit_loss"] = total_pnl if data["summaries"] else 0
    save_state()
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"Monitor Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    print(f"Cycles monitored: {current_cycle}")
    print(f"Total closed trades: {len(state['closed_trades'])}")
    print(f"Current balance: £{total_value if data['summaries'] else 'N/A'}")
    print(f"Highest balance: £{state['highest_balance']:.2f}")
    print(f"Total P&L: £{state['total_profit_loss']:+.2f}")
    print(f"{'='*50}")

if __name__ == "__main__":
    check_and_notify()
