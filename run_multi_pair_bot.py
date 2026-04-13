#!/usr/bin/env python3
"""
Multi-Pair Bot Launcher
======================

Convenient launcher that supports:
- Starting the bot in dry-run or live mode
- Attaching the trade monitor
- Generating reports

Usage:
    python3 run_multi_pair_bot.py --dry-run
    python3 run_multi_pair_bot.py --live --capital 500
    python3 run_multi_pair_bot.py --report
    python3 run_multi_pair_bot.py --monitor
"""

import argparse
import sys
import subprocess
from pathlib import Path

def run_bot(dry_run, capital=None, max_pairs=None):
    """Launch the multi-pair bot"""
    cmd = [sys.executable, str(Path(__file__).parent / "simple_multi_bot.py")]
    if dry_run:
        cmd.append("--dry-run")
    if capital:
        cmd.extend(["--capital", str(capital)])
    if max_pairs:
        cmd.extend(["--max-positions", str(max_pairs)])
    
    print(f"Launching bot: {' '.join(cmd)}")
    subprocess.run(cmd)

def run_v5(dry_run, capital=None, max_pairs=None):
    """Launch the advanced v5 multi-pair bot"""
    cmd = [sys.executable, str(Path(__file__).parent / "multi_pair_portfolio_trader_v5.py")]
    if dry_run:
        cmd.append("--dry-run")
    if capital:
        cmd.extend(["--capital", str(capital)])
    if max_pairs:
        cmd.extend(["--max-pairs", str(max_pairs)])
    
    print(f"Launching v5 bot: {' '.join(cmd)}")
    subprocess.run(cmd)

def run_monitor():
    """Run the trade monitor once"""
    cmd = [sys.executable, str(Path(__file__).parent / "multi_bot_monitor.py")]
    print(f"Running monitor: {' '.join(cmd)}")
    subprocess.run(cmd)

def run_report():
    """Generate performance report"""
    cmd = [sys.executable, str(Path(__file__).parent / "multi_bot_report.py")]
    print(f"Generating report: {' '.join(cmd)}")
    subprocess.run(cmd)

def main():
    parser = argparse.ArgumentParser(description="Multi-Pair Bot Launcher")
    parser.add_argument("--dry-run", action="store_true", help="Run in simulation mode")
    parser.add_argument("--live", action="store_true", help="Run in live mode (real trades)")
    parser.add_argument("--v5", action="store_true", help="Use advanced v5 bot")
    parser.add_argument("--capital", type=int, default=None, help="Starting capital")
    parser.add_argument("--max-pairs", type=int, default=None, help="Max concurrent pairs")
    parser.add_argument("--monitor", action="store_true", help="Run monitor")
    parser.add_argument("--report", action="store_true", help="Generate report")
    
    args = parser.parse_args()
    
    if args.monitor:
        run_monitor()
        return
    
    if args.report:
        run_report()
        return
    
    if args.live or args.dry_run:
        if args.v5:
            run_v5(dry_run=not args.live, capital=args.capital, max_pairs=args.max_pairs)
        else:
            run_bot(dry_run=not args.live, capital=args.capital, max_pairs=args.max_pairs)
    else:
        print("Please specify --dry-run, --live, --monitor, or --report")
        parser.print_help()

if __name__ == "__main__":
    main()
