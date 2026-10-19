"""Backtests. Both paths are simulated; neither sends an order.

`run` is the original Aroon study (a tie counts as Down).
`signal_backtest` is the research definition (Up if close >= open) for any
fixed library signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aroonbot.agents import DOWN, UP, PaperExecutionAgent, RiskAgent, SignalAgent, SizerAgent
from aroonbot.research import attach_features, window_frame
from aroonbot.signals import SIGNAL_NEEDS, as_direction, features, library


def window_outcomes(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    opened = df["open"].resample(f"{minutes}min").first()
    closed = df["close"].resample(f"{minutes}min").last()
    count = df["close"].resample(f"{minutes}min").count()
    frame = pd.DataFrame({"start": opened, "end": closed, "n": count})
    return frame[frame.n == minutes]


def run(
    df: pd.DataFrame,
    minutes: int = 60,
    period: int = 14,
    threshold: float = 25,
    entry: float = 0.50,
    fee: float = 0.02,
    cfg_risk: dict | None = None,
    cfg_size: dict | None = None,
) -> dict:
    signal, _osc = SignalAgent(period, threshold).signals(df)
    signal_prev = signal.shift(1)
    frame = window_outcomes(df, minutes)
    frame["signal"] = signal_prev.reindex(frame.index)
    frame["up"] = frame.end > frame.start
    trades = frame[frame.signal.isin([UP, DOWN])].copy()
    trades["win"] = ((trades.signal == UP) & trades.up) | ((trades.signal == DOWN) & ~trades.up)
    per_share = trades.win.astype(float) - (entry + fee)
    risk = RiskAgent(**(cfg_risk or {}))
    sizer = SizerAgent(**(cfg_size or {}))
    execution = PaperExecutionAgent(entry, fee)
    taken = 0
    for ts, row in trades.iterrows():
        day = ts.date()
        if not risk.can_open(day, 0):
            continue
        position = execution.open(row.signal, sizer.stake(risk.bankroll), ts, ts)
        pnl, _win = execution.settle(position, row.start, row.end)
        risk.record(day, pnl)
        taken += 1
    return {
        "minutes": minutes,
        "windows": len(frame),
        "trades": len(trades),
        "base_rate_up": float(frame.up.mean()) if len(frame) else float("nan"),
        "hit_rate": float(trades.win.mean()) if len(trades) else float("nan"),
        "pnl_per_share_avg": float(per_share.mean()) if len(trades) else float("nan"),
        "flat_10usd_total": float((per_share / (entry + fee) * 10).sum()) if len(trades) else 0.0,
        "sim_trades": taken,
        "sim_final_bankroll": risk.bankroll,
        "sim_killed": risk.killed,
    }


def _downsample(rows: list[dict], max_points: int = 600) -> list[dict]:
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    indexes = {min(int(i * step), len(rows) - 1) for i in range(max_points)}
    indexes.add(len(rows) - 1)
    return [rows[i] for i in sorted(indexes)]


def prediction_frame(
    df: pd.DataFrame,
    signal: str,
    minutes: int,
    eval_start=None,
    eval_end=None,
) -> pd.DataFrame:
    """Window rows with a `pred` column. Features are the prior closed bar."""
    rules = library()
    if signal not in rules:
        raise ValueError(f"unknown signal {signal!r}")
    needs = SIGNAL_NEEDS[signal]
    feats = features(df)
    missing = [col for col in needs if col not in feats.columns]
    if missing:
        raise ValueError(f"{signal} needs columns {missing}, which this data does not have")
    frame = attach_features(window_frame(df, minutes), feats, needs)
    if eval_start is not None:
        frame = frame[frame.index >= pd.Timestamp(eval_start)]
    if eval_end is not None:
        frame = frame[frame.index < pd.Timestamp(eval_end)]
    if frame.empty:
        raise ValueError("no complete windows in that range (indicators may still be warming up)")
    frame = frame.copy()
    frame["pred"] = np.asarray(rules[signal](frame))
    return frame


def signal_backtest(
    df: pd.DataFrame,
    signal: str,
    minutes: int = 15,
    entry: float = 0.50,
    fee: float = 0.01,
    spread: float = 0.0,
    eval_start=None,
    eval_end=None,
    cfg_risk: dict | None = None,
    cfg_size: dict | None = None,
) -> dict:
    if signal not in library():
        known = ", ".join(library())
        raise ValueError(f"unknown signal {signal!r}. Interactive signals: {known}")
    frame = prediction_frame(df, signal, minutes, eval_start, eval_end)
    pred = frame["pred"].to_numpy()
    mask = pred != 0
    traded = frame.loc[mask].copy()
    pred_t = pred[mask]
    win = ((pred_t == 1) & (traded.up.to_numpy() == 1)) | ((pred_t == -1) & (traded.up.to_numpy() == 0))
    cost = float(entry + fee + spread)
    pnl = win.astype(float) - cost
    n = int(len(traded))
    hit = float(win.mean()) if n else float("nan")
    se_null = float(np.sqrt(0.25 / n)) if n else float("nan")
    z50 = (hit - 0.5) / se_null if n else float("nan")
    z_be = (hit - cost) / se_null if n else float("nan")
    pnl_se = float(np.std(pnl, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    equity = []
    if n:
        cumulative = np.cumsum(pnl)
        for ts, value in zip(traded.index, cumulative, strict=True):
            equity.append({"t": pd.Timestamp(ts).isoformat(), "cum_pnl_per_share": float(value)})
    risk = RiskAgent(**(cfg_risk or {}))
    sizer = SizerAgent(**(cfg_size or {}))
    bankroll_path = []
    taken = 0
    killed_at = None
    for ts, win_i in zip(traded.index, win, strict=True):
        day = pd.Timestamp(ts).date()
        if not risk.can_open(day, 0):
            continue
        stake = sizer.stake(risk.bankroll)
        if stake <= 0 or cost <= 0:
            continue
        shares = stake / cost
        dollars = shares * (1.0 if win_i else 0.0) - stake
        risk.record(day, float(dollars))
        taken += 1
        bankroll_path.append({"t": pd.Timestamp(ts).isoformat(), "bankroll": float(risk.bankroll)})
        if risk.killed and killed_at is None:
            killed_at = pd.Timestamp(ts).isoformat()
    recent = []
    if n:
        tail = traded.iloc[-30:]
        tail_pred = pred_t[-len(tail) :]
        tail_win = win[-len(tail) :]
        tail_pnl = pnl[-len(tail) :]
        for ts, direction, did_win, pnl_i in zip(tail.index, tail_pred, tail_win, tail_pnl, strict=True):
            recent.append(
                {
                    "t": pd.Timestamp(ts).isoformat(),
                    "signal": "UP" if as_direction(direction) == 1 else "DOWN",
                    "outcome": "UP" if int(traded.loc[ts, "up"]) == 1 else "DOWN",
                    "win": bool(did_win),
                    "pnl_per_share": float(pnl_i),
                }
            )
    return {
        "paper_only": True,
        "signal": signal,
        "minutes": minutes,
        "windows": int(len(frame)),
        "trades": n,
        "base_rate_up": float(frame.up.mean()),
        "hit_rate": hit,
        "breakeven_hit_rate": cost,
        "hit_minus_breakeven": (hit - cost) if n else float("nan"),
        "entry": float(entry),
        "fee": float(fee),
        "spread": float(spread),
        "cost_per_share": cost,
        "pnl_per_share": float(pnl.mean()) if n else float("nan"),
        "pnl_se": pnl_se,
        "z_vs_50": z50,
        "z_vs_breakeven": z_be,
        "z_note": "z uses the study's null standard error sqrt(0.25 / n), not the empirical standard error.",
        "equity": _downsample(equity),
        "bankroll": _downsample(bankroll_path),
        "sim_trades": taken,
        "sim_final_bankroll": float(risk.bankroll),
        "sim_killed": bool(risk.killed),
        "sim_killed_at": killed_at,
        "recent_trades": recent,
        "assumptions": [
            "Paper simulation on Binance BTCUSDT 1-minute bars.",
            "The signal uses the last closed bar before the window open.",
            "Up means the window close is greater than or equal to the open.",
            "Per-share PnL is 1 - entry - fee - spread on a win, and 0 - entry - fee - spread on a loss.",
            "This is not a Polymarket fill. Real entry prices are a separate check.",
        ],
    }
