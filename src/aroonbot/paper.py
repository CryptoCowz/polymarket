"""Append-only local log of simulated decisions. Nothing here is an order."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from aroonbot.agents import RiskAgent, SizerAgent
from aroonbot.polymarket import floor_window, last_at_or_before, taker_fee
from aroonbot.signals import as_direction, features, library

UP = 1


def direction_name(direction: int) -> str:
    return {1: "UP", -1: "DOWN", 0: "NEUTRAL"}[direction]


class PaperLog:
    def __init__(self, path: str | Path = "data/paper_log.jsonl"):
        self.path = Path(path)

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(row, default=str) + "\n" for row in rows))
        tmp.replace(self.path)

    def upsert(self, row: dict) -> list[dict]:
        rows = self.read()
        replaced = False
        for i, existing in enumerate(rows):
            if existing.get("id") == row["id"]:
                rows[i] = row
                replaced = True
                break
        if not replaced:
            rows.append(row)
        self.write(rows)
        return rows


def _feature_row(df: pd.DataFrame, window_start: pd.Timestamp):
    feats = features(df)
    ts = window_start - pd.Timedelta(minutes=1)
    prior = feats.loc[:ts]
    if prior.empty:
        raise ValueError("not enough closed bars to compute a signal")
    return prior.index[-1], prior.iloc[[-1]]


def _finite(value):
    number = float(value)
    if number != number:
        return None
    return number


def signals_at(df: pd.DataFrame, window_start: pd.Timestamp) -> dict:
    used, row = _feature_row(df, window_start)
    readings = {}
    for name, fn in library().items():
        try:
            readings[name] = direction_name(as_direction(np.asarray(fn(row))[0]))
        except (ValueError, KeyError):
            readings[name] = None
    bar = df.loc[used]
    return {
        "asof": pd.Timestamp(used).isoformat(),
        "rsi": _finite(row["rsi"].iloc[0]),
        "aroon": _finite(row["aroon"].iloc[0]),
        "bb_z": _finite(row["bb_z"].iloc[0]) if "bb_z" in row else None,
        "btc_close": float(bar["close"]),
        "signals": readings,
    }


def signal_at(df: pd.DataFrame, window_start: pd.Timestamp, signal: str) -> dict:
    used, row = _feature_row(df, window_start)
    direction = as_direction(np.asarray(library()[signal](row))[0])
    bar = df.loc[used]
    return {
        "asof": pd.Timestamp(used).isoformat(),
        "signal": direction_name(direction),
        "direction": direction,
        "rsi": _finite(row["rsi"].iloc[0]),
        "aroon": _finite(row["aroon"].iloc[0]),
        "btc_close": float(bar["close"]),
    }


def window_prices(df: pd.DataFrame, window_start: pd.Timestamp, minutes: int) -> dict | None:
    end = window_start + pd.Timedelta(minutes=minutes)
    bars = df[(df.index >= window_start) & (df.index < end)]
    if len(bars) < minutes:
        return None
    opened = float(bars.iloc[0]["open"])
    closed = float(bars.iloc[-1]["close"])
    return {"btc_open": opened, "btc_close": closed, "btc_up": closed >= opened}


def entry_from_market(market: dict, direction: int) -> dict | None:
    if not market or not market.get("ok"):
        return None
    start_ts = int(market["start_ts"])
    if direction == UP:
        price = last_at_or_before(market.get("up_history") or [], start_ts)
        source = "polymarket_up_print_at_or_before_open"
    else:
        price = last_at_or_before(market.get("down_history") or [], start_ts)
        source = "polymarket_down_print_at_or_before_open"
        if price is None:
            up = last_at_or_before(market.get("up_history") or [], start_ts)
            if up is None:
                return None
            price = 1.0 - up
            source = "inferred_as_one_minus_up_print"
    if price is None:
        return None
    return {"entry": float(price), "entry_source": source}


def settle_row(row: dict, prices: dict | None, market: dict | None) -> dict:
    row = dict(row)
    if prices is not None:
        row["btc_open"] = prices["btc_open"]
        row["btc_close"] = prices["btc_close"]
        row["btc_up"] = prices["btc_up"]
    if market and market.get("resolved"):
        row["pm_settled_up"] = market.get("settled_up")
    if row.get("signal") in (None, "NEUTRAL") or row.get("entry") is None:
        row["status"] = row.get("status") or "skip"
        return row
    if prices is None:
        row["status"] = "open"
        return row
    win = (row["signal"] == "UP" and prices["btc_up"]) or (row["signal"] == "DOWN" and not prices["btc_up"])
    row["win"] = bool(win)
    cost = float(row["entry"]) + float(row["fee"]) + float(row.get("spread") or 0.0)
    row["pnl_per_share"] = (1.0 if win else 0.0) - cost
    row["status"] = "settled"
    row["settlement"] = "binance_close_ge_open"
    return row


def fee_for(entry: float, fee_model: str, flat_fee: float, taker_rate: float) -> float:
    if fee_model == "polymarket_taker":
        return taker_fee(entry, taker_rate)
    if fee_model == "flat":
        if flat_fee < 0:
            raise ValueError("flat fee must be non-negative")
        return float(flat_fee)
    raise ValueError("fee_model must be flat or polymarket_taker")


def build_decision(
    df: pd.DataFrame,
    *,
    minutes: int,
    signal: str,
    now,
    entry_mode: str,
    fee_model: str,
    flat_fee: float,
    taker_rate: float,
    market: dict | None,
) -> dict:
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    start = floor_window(now, minutes)
    end = start + pd.Timedelta(minutes=minutes)
    snap = signal_at(df, start, signal)
    row = {
        "id": f"{signal}-{minutes}m-{int(start.timestamp())}",
        "paper_only": True,
        "logged_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "minutes": minutes,
        "signal_name": signal,
        "signal": snap["signal"],
        "rsi": snap["rsi"],
        "aroon": snap["aroon"],
        "feature_asof": snap["asof"],
        "spread": 0.0,
        "note": "Simulated decision. No order was sent.",
    }
    if snap["direction"] == 0:
        row.update({"status": "skip", "entry": None, "fee": None, "entry_source": None, "pnl_per_share": None})
        return settle_row(row, window_prices(df, start, minutes), market)
    if entry_mode == "half":
        entry = 0.50
        source = "assumed_0.50"
    elif entry_mode == "polymarket_print":
        found = entry_from_market(market or {}, snap["direction"])
        if found is None:
            row.update(
                {
                    "status": "no_price",
                    "entry": None,
                    "fee": None,
                    "entry_source": None,
                    "pnl_per_share": None,
                    "note": "No public print at the open, so no simulated entry price was invented.",
                }
            )
            return row
        entry = found["entry"]
        source = found["entry_source"]
    else:
        raise ValueError("entry_mode must be half or polymarket_print")
    row["entry"] = entry
    row["entry_source"] = source
    row["fee"] = fee_for(entry, fee_model, flat_fee, taker_rate)
    row["fee_model"] = fee_model
    return settle_row(row, window_prices(df, start, minutes), market)


def summarize_log(rows: list[dict], risk: dict | None = None, sizing: dict | None = None) -> dict:
    settled = [row for row in rows if row.get("status") == "settled" and row.get("pnl_per_share") is not None]
    wins = [row for row in settled if row.get("win")]
    agent = RiskAgent(**(risk or {}))
    sizer = SizerAgent(**(sizing or {}))
    ordered = sorted(settled, key=lambda row: row.get("window_start") or "")
    for row in ordered:
        day = pd.Timestamp(row["window_start"]).date()
        if not agent.can_open(day, 0):
            continue
        stake = sizer.stake(agent.bankroll)
        cost = float(row["entry"]) + float(row["fee"]) + float(row.get("spread") or 0.0)
        if stake <= 0 or cost <= 0:
            continue
        shares = stake / cost
        dollars = shares * ((1.0 if row["win"] else 0.0) - cost) + 0.0
        # shares * payout - stake, and stake = shares * cost, so dollars = shares * (payout - cost)
        agent.record(day, dollars)
    return {
        "n": len(rows),
        "settled": len(settled),
        "open": sum(1 for row in rows if row.get("status") == "open"),
        "skips": sum(1 for row in rows if row.get("status") == "skip"),
        "hit_rate": (len(wins) / len(settled)) if settled else None,
        "avg_pnl_per_share": float(np.mean([row["pnl_per_share"] for row in settled])) if settled else None,
        "sim_final_bankroll": float(agent.bankroll),
        "sim_killed": bool(agent.killed),
    }
