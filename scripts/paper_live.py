"""Print the current paper signal on a loop. No orders and no keys."""

from __future__ import annotations

import argparse
import time

import pandas as pd

from aroonbot.config import load_config
from aroonbot.data import load_klines
from aroonbot.paper import signals_at
from aroonbot.polymarket import floor_window


def once(minutes: int) -> None:
    cfg = load_config()
    now = pd.Timestamp.now(tz="UTC")
    frame = load_klines(
        now - pd.Timedelta(hours=48),
        now + pd.Timedelta(minutes=1),
        symbol=cfg.get("symbol", "BTCUSDT"),
        warmup=pd.Timedelta(0),
    )
    start = floor_window(now, minutes)
    reading = signals_at(frame, start)
    side = reading["signals"].get(cfg.get("default_signal", "rsi_mr_30_70"))
    print(
        now.isoformat(),
        f"window={start.isoformat()}",
        f"rsi={reading['rsi']:.1f}" if reading["rsi"] is not None else "rsi=nan",
        f"signal={side}",
        f"btc={reading['btc_close']:.1f}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper signal loop. Does not trade.")
    parser.add_argument("--minutes", type=int, default=15, choices=(5, 15, 60))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        once(args.minutes)
        if args.once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
