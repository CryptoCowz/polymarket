"""Download and cache BTCUSDT 1-minute bars, then write data/btc_1m_long.pkl."""

from __future__ import annotations

import argparse

import pandas as pd

from aroonbot.data import load_klines


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache public Binance BTCUSDT 1m klines.")
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2026-10-19", help="Inclusive UTC date.")
    args = parser.parse_args()
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)
    frame = load_klines(start, end, warmup=pd.Timedelta(0))
    frame = frame[(frame.index >= start) & (frame.index < end)]
    path = "data/btc_1m_long.pkl"
    frame.to_pickle(path)
    print(len(frame), frame.index[0], frame.index[-1], path)


if __name__ == "__main__":
    main()
