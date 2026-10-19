"""Run a paper backtest on public BTCUSDT klines. No orders."""

from __future__ import annotations

import argparse
import json

import pandas as pd

from aroonbot.backtest import run, signal_backtest
from aroonbot.config import load_config
from aroonbot.data import load_klines


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper backtest. No orders are sent.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--end", default=None, help="UTC date, inclusive. Default: today.")
    parser.add_argument("--signal", default="rsi_mr_30_70")
    parser.add_argument("--minutes", type=int, default=15, choices=(5, 15, 60))
    parser.add_argument("--entry", type=float, default=0.50)
    parser.add_argument("--fee", type=float, default=0.01)
    parser.add_argument("--legacy-aroon", action="store_true", help="Original Aroon path (tie counts as Down).")
    args = parser.parse_args()
    load_config()
    end_day = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC").floor("D")
    end = end_day + pd.Timedelta(days=1)
    start = end_day - pd.Timedelta(days=args.days - 1)
    frame = load_klines(start, end)
    print(f"bars={len(frame)} {frame.index[0]} -> {frame.index[-1]}")
    if args.legacy_aroon:
        for minutes in (60, 15, 5):
            for fee in (0.01, 0.03):
                print(json.dumps(run(frame, minutes, fee=fee), default=str))
        return
    result = signal_backtest(
        frame,
        args.signal,
        minutes=args.minutes,
        entry=args.entry,
        fee=args.fee,
        eval_start=start,
        eval_end=end,
    )
    result.pop("equity", None)
    result.pop("bankroll", None)
    result.pop("recent_trades", None)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
