"""Replay the experimental maker paper test against public prices-history."""

from __future__ import annotations

import argparse
import json

import pandas as pd

from aroonbot.config import load_config
from aroonbot.data import load_klines
from aroonbot.maker import evaluate_plan, plan_windows
from aroonbot.polymarket import PublicPolymarket


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper maker replay. No orders are sent.")
    parser.add_argument("--minutes", type=int, default=15, choices=(5, 15, 60))
    parser.add_argument("--windows", type=int, default=16)
    parser.add_argument("--shade", type=float, default=0.02)
    parser.add_argument("--anchor", default="open_print", choices=("open_print", "half"))
    parser.add_argument("--rebate", type=float, default=0.0)
    parser.add_argument("--signal", default="rsi_mr_30_70")
    parser.add_argument("--max-markets", type=int, default=16)
    args = parser.parse_args()
    cfg = load_config()
    now = pd.Timestamp.now(tz="UTC")
    lookback = pd.Timedelta(minutes=args.minutes * args.windows + 60)
    frame = load_klines(
        now - lookback,
        now + pd.Timedelta(minutes=1),
        symbol=cfg.get("symbol", "BTCUSDT"),
    )
    plan = plan_windows(frame, args.minutes, args.windows, now=now, signal=args.signal)
    pending = [item for item in plan if item["status"] == "pending"]
    if len(pending) > args.max_markets:
        keep = {item["window"] for item in pending[-args.max_markets :]}
        for item in plan:
            if item["status"] == "pending" and item["window"] not in keep:
                item["status"] = "capped"
    client = PublicPolymarket()
    markets = {}
    for item in plan:
        if item["status"] != "pending":
            continue
        markets[item["window"]] = client.window(item["ts"], args.minutes)
    result = evaluate_plan(plan, markets, args.minutes, args.shade, args.anchor, args.rebate)
    print(json.dumps({"summary": result["summary"], "n_rows": len(result["rows"])}, default=str))
    for row in result["rows"]:
        if row.get("status") in ("filled", "resting_unfilled", "marketable_not_counted"):
            print(
                row["window"],
                row.get("signal"),
                row.get("status"),
                row.get("limit"),
                row.get("pnl_per_share"),
            )


if __name__ == "__main__":
    main()
