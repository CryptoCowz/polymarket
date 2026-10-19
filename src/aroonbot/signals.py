"""Pluggable signal library.

Every feature at bar t uses only bars at or before t. A signal maps a feature
frame to a score array: +1 UP, -1 DOWN, 0 neutral.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

DESCRIPTIONS: dict[str, str] = {
    "aroon_trend_25": "Aroon oscillator trend. UP if osc > 25, DOWN if osc < -25.",
    "aroon_reversal_25": "Fade the Aroon oscillator. Opposite of the trend rule.",
    "reversal_1m": "Fade the previous 1-minute log return.",
    "reversal_5m": "Fade the previous 5-minute log return.",
    "reversal_15m": "Fade the previous 15-minute log return.",
    "reversal_60m": "Fade the previous 60-minute log return.",
    "tsmom_60m": "Follow the previous 60-minute log return.",
    "tsmom_240m": "Follow the previous 4-hour log return.",
    "tsmom_1440m": "Follow the previous 1-day log return.",
    "tsmom_multi_vote": "Vote of 60-minute, 4-hour, and 1-day returns. Trade when at least two agree.",
    "rsi_mr_30_70": "RSI(14) mean reversion. UP if RSI < 30, DOWN if RSI > 70.",
    "bb_mr_2sd": "Bollinger mean reversion. UP below the 20-bar mean by 2 SD, DOWN above it.",
    "reversal_15m_highvol": "Fade the 15-minute return only when 60-minute vol exceeds 1.2× daily vol.",
    "reversal_15m_lowvol": "Fade the 15-minute return only when 60-minute vol is below 0.8× daily vol.",
    "tsmom_240m_highvol": "Follow the 4-hour return only in that high-vol regime.",
    "imb_follow_5m": "Follow 5-minute taker-buy imbalance (absolute threshold 0.05).",
    "imb_follow_15m": "Follow 15-minute taker-buy imbalance (absolute threshold 0.05).",
    "imb_follow_60m": "Follow 60-minute taker-buy imbalance (absolute threshold 0.05).",
    "imb_fade_5m": "Fade 5-minute taker-buy imbalance (absolute threshold 0.05).",
    "imb_fade_15m": "Fade 15-minute taker-buy imbalance (absolute threshold 0.05).",
    "imb_fade_60m": "Fade 60-minute taker-buy imbalance (absolute threshold 0.05).",
    "season_how_52": "Hour-of-week seasonality fit on the training split only. Not refit in the UI.",
    "ensemble_logit_m0.0": "Train-only logistic regression. Any probability off 0.5 is a trade.",
    "ensemble_logit_m0.01": "Train-only logistic regression with confidence margin 0.01.",
    "ensemble_logit_m0.02": "Train-only logistic regression with confidence margin 0.02.",
    "ensemble_logit_m0.05": "Train-only logistic regression with confidence margin 0.05.",
    "vote_oriented_all": "Sign-sum of base signals, each oriented by its training hit rate.",
}

FAMILIES: dict[str, str] = {
    "aroon_trend_25": "trend",
    "aroon_reversal_25": "mean_reversion",
    "reversal_1m": "mean_reversion",
    "reversal_5m": "mean_reversion",
    "reversal_15m": "mean_reversion",
    "reversal_60m": "mean_reversion",
    "tsmom_60m": "trend",
    "tsmom_240m": "trend",
    "tsmom_1440m": "trend",
    "tsmom_multi_vote": "trend",
    "rsi_mr_30_70": "mean_reversion",
    "bb_mr_2sd": "mean_reversion",
    "reversal_15m_highvol": "mean_reversion",
    "reversal_15m_lowvol": "mean_reversion",
    "tsmom_240m_highvol": "trend",
    "imb_follow_5m": "imbalance",
    "imb_follow_15m": "imbalance",
    "imb_follow_60m": "imbalance",
    "imb_fade_5m": "imbalance",
    "imb_fade_15m": "imbalance",
    "imb_fade_60m": "imbalance",
    "season_how_52": "seasonality",
    "ensemble_logit_m0.0": "ensemble",
    "ensemble_logit_m0.01": "ensemble",
    "ensemble_logit_m0.02": "ensemble",
    "ensemble_logit_m0.05": "ensemble",
    "vote_oriented_all": "ensemble",
}

# Columns a signal reads. Interactive backtests drop windows missing these.
SIGNAL_NEEDS: dict[str, list[str]] = {
    "aroon_trend_25": ["aroon"],
    "aroon_reversal_25": ["aroon"],
    "reversal_1m": ["ret_1"],
    "reversal_5m": ["ret_5"],
    "reversal_15m": ["ret_15"],
    "reversal_60m": ["ret_60"],
    "tsmom_60m": ["ret_60"],
    "tsmom_240m": ["ret_240"],
    "tsmom_1440m": ["ret_1440"],
    "tsmom_multi_vote": ["ret_60", "ret_240", "ret_1440"],
    "rsi_mr_30_70": ["rsi"],
    "bb_mr_2sd": ["bb_z"],
    "reversal_15m_highvol": ["vol_ratio", "ret_15"],
    "reversal_15m_lowvol": ["vol_ratio", "ret_15"],
    "tsmom_240m_highvol": ["vol_ratio", "ret_240"],
    "imb_follow_5m": ["imb_5"],
    "imb_follow_15m": ["imb_15"],
    "imb_follow_60m": ["imb_60"],
    "imb_fade_5m": ["imb_5"],
    "imb_fade_15m": ["imb_15"],
    "imb_fade_60m": ["imb_60"],
}

ENSEMBLE_COLS = [
    "ret_1",
    "ret_5",
    "ret_15",
    "ret_60",
    "ret_240",
    "ret_1440",
    "aroon",
    "rsi",
    "bb_z",
    "vol_ratio",
    "imb_5",
    "imb_15",
    "imb_60",
]

STUDY_ONLY = {
    "season_how_52",
    "ensemble_logit_m0.0",
    "ensemble_logit_m0.01",
    "ensemble_logit_m0.02",
    "ensemble_logit_m0.05",
    "vote_oriented_all",
}


def fast_aroon_osc(high: pd.Series, low: pd.Series, period: int = 14) -> pd.Series:
    window = period + 1
    highs = high.to_numpy()
    lows = low.to_numpy()
    out = np.full(len(highs), np.nan)
    if len(highs) >= window:
        arg_high = np.argmax(sliding_window_view(highs, window), axis=1)
        arg_low = np.argmin(sliding_window_view(lows, window), axis=1)
        out[window - 1 :] = 100.0 * (arg_high - arg_low) / period
    return pd.Series(out, index=high.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    log_close = np.log(close)
    frame = pd.DataFrame(index=df.index)
    for k in (1, 5, 15, 60, 240, 1440):
        frame[f"ret_{k}"] = log_close - log_close.shift(k)
    frame["aroon"] = fast_aroon_osc(df["high"], df["low"], 14)
    frame["rsi"] = rsi(close, 14)
    mean = close.rolling(20).mean()
    std = close.rolling(20).std()
    frame["bb_z"] = (close - mean) / std
    bar_returns = log_close.diff()
    frame["vol_60"] = bar_returns.rolling(60).std()
    frame["vol_1440"] = bar_returns.rolling(1440).std()
    frame["vol_ratio"] = frame.vol_60 / frame.vol_1440
    if "taker_buy" in df:
        for k in (5, 15, 60):
            volume = df["volume"].rolling(k).sum()
            taker = df["taker_buy"].rolling(k).sum()
            frame[f"imb_{k}"] = (2 * taker - volume) / volume.replace(0, np.nan)
    frame["how"] = df.index.dayofweek * 24 + df.index.hour
    return frame


def _sign(values, threshold: float = 0.0):
    arr = np.asarray(values, dtype=float)
    return np.where(arr > threshold, 1, np.where(arr < -threshold, -1, 0))


def library(train_feats: pd.DataFrame | None = None, train_up: pd.Series | None = None):
    """Name -> callable(feature frame) -> array of {-1, 0, 1}.

    Thresholds are fixed in advance. The seasonality rule is the only one that
    estimates a parameter, and it uses the training split only.
    """
    rules = {}
    rules["rsi_mr_30_70"] = lambda f: np.where(f.rsi < 30, 1, np.where(f.rsi > 70, -1, 0))
    rules["bb_mr_2sd"] = lambda f: np.where(f.bb_z < -2, 1, np.where(f.bb_z > 2, -1, 0))
    rules["aroon_trend_25"] = lambda f: _sign(f.aroon.to_numpy(), 25)
    rules["aroon_reversal_25"] = lambda f: -_sign(f.aroon.to_numpy(), 25)
    for k in (1, 5, 15, 60):
        rules[f"reversal_{k}m"] = (lambda k: lambda f: -_sign(f[f"ret_{k}"].to_numpy()))(k)
    for k in (60, 240, 1440):
        rules[f"tsmom_{k}m"] = (lambda k: lambda f: _sign(f[f"ret_{k}"].to_numpy()))(k)
    rules["tsmom_multi_vote"] = lambda f: _sign(
        np.sign(f.ret_60) + np.sign(f.ret_240) + np.sign(f.ret_1440), 1
    )
    rules["reversal_15m_highvol"] = lambda f: np.where(
        f.vol_ratio > 1.2, -_sign(f.ret_15.to_numpy()), 0
    )
    rules["reversal_15m_lowvol"] = lambda f: np.where(
        f.vol_ratio < 0.8, -_sign(f.ret_15.to_numpy()), 0
    )
    rules["tsmom_240m_highvol"] = lambda f: np.where(
        f.vol_ratio > 1.2, _sign(f.ret_240.to_numpy()), 0
    )
    for k in (5, 15, 60):
        rules[f"imb_follow_{k}m"] = (lambda k: lambda f: _sign(f[f"imb_{k}"].to_numpy(), 0.05))(k)
        rules[f"imb_fade_{k}m"] = (lambda k: lambda f: -_sign(f[f"imb_{k}"].to_numpy(), 0.05))(k)
    if train_feats is not None and train_up is not None:
        grouped = pd.Series(train_up.to_numpy(), index=train_feats.how.to_numpy())
        rate = grouped.groupby(level=0).mean()
        rules["season_how_52"] = lambda f: _sign(f.how.map(rate).fillna(0.5).to_numpy() - 0.5, 0.02)
    return rules


def as_direction(value) -> int:
    direction = int(value)
    if direction not in (-1, 0, 1):
        raise ValueError(f"signal returned {value!r}")
    return direction


def describe(name: str) -> str:
    return DESCRIPTIONS.get(name, name)


def family(name: str) -> str:
    return FAMILIES.get(name, "other")
