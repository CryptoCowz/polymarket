"""Train / validation / test harness for Up/Down windows.

Features on a window are taken from the last closed 1-minute bar before the
window opens. Up means close >= open, matching Polymarket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from aroonbot.signals import ENSEMBLE_COLS, features, library


def window_frame(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    opened = df["open"].resample(f"{minutes}min").first()
    closed = df["close"].resample(f"{minutes}min").last()
    count = df["close"].resample(f"{minutes}min").count()
    frame = pd.DataFrame({"start": opened, "end": closed, "n": count})
    frame = frame[frame.n == minutes]
    frame["up"] = (frame.end >= frame.start).astype(int)
    return frame


def attach_features(frame: pd.DataFrame, feats: pd.DataFrame, columns: list[str] | None = None):
    shifted = feats.shift(1).reindex(frame.index)
    out = frame.join(shifted)
    if columns:
        out = out.dropna(subset=list(columns))
    return out


def windows(df: pd.DataFrame, feats: pd.DataFrame, minutes: int) -> pd.DataFrame:
    frame = window_frame(df, minutes)
    return attach_features(frame, feats).dropna(subset=["ret_1440", "vol_1440"])


def score(pred, up, fees=(0.01, 0.03), entry: float = 0.50) -> dict:
    pred = np.asarray(pred)
    up = np.asarray(up)
    mask = pred != 0
    n = int(mask.sum())
    if n == 0:
        return {"trades": 0, "hit": np.nan}
    win = ((pred[mask] == 1) & (up[mask] == 1)) | ((pred[mask] == -1) & (up[mask] == 0))
    hit = float(win.mean())
    se = float(np.sqrt(0.25 / n))
    z = (hit - 0.5) / se
    out = {"trades": n, "hit": hit, "z_vs_50": z, "p_one_sided": float(1 - norm.cdf(z))}
    for fee in fees:
        out[f"pnl_sh_{int(fee * 100)}c"] = hit - (entry + fee)
        out[f"z_vs_breakeven_{int(fee * 100)}c"] = (hit - (entry + fee)) / se
    return out


def ensemble_fit(train: pd.DataFrame):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
    model.fit(train[ENSEMBLE_COLS].fillna(0), train.up)
    return model


def ensemble_pred(model, frame: pd.DataFrame, margin: float):
    probability = model.predict_proba(frame[ENSEMBLE_COLS].fillna(0))[:, 1]
    return np.where(probability > 0.5 + margin, 1, np.where(probability < 0.5 - margin, -1, 0))


def build_rules(train: pd.DataFrame):
    """Study rule set: fixed library, train-only seasonality, train-only logit, oriented vote."""
    rules = library(train, train.up)
    model = ensemble_fit(train)
    for margin in (0.0, 0.01, 0.02, 0.05):
        rules[f"ensemble_logit_m{margin}"] = (lambda margin: lambda d: ensemble_pred(model, d, margin))(
            margin
        )
    base = [name for name in rules if not name.startswith("ensemble")]

    def _orient(name: str) -> float:
        hit = score(rules[name](train), train.up.to_numpy()).get("hit", 0.5)
        if hit != hit:
            return 0.0
        return float(np.sign(hit - 0.5))

    orientation = {name: _orient(name) for name in base}

    def vote(frame):
        total = sum(orientation[name] * np.asarray(rules[name](frame)) for name in base)
        return np.sign(total)

    rules["vote_oriented_all"] = vote
    return rules


def run_study(df: pd.DataFrame, splits: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame:
    """Evaluate every rule on train and validation, then the single selected rule on test.

    Post-hoc test rows are stored for transparency and are not a clean test.
    """
    splits = splits or {
        "train": ("2022-01-01", "2025-01-01"),
        "val": ("2025-01-01", "2026-01-01"),
        "test": ("2026-01-01", "2026-10-19"),
    }
    feats = features(df)
    rows: list[dict] = []
    for minutes in (5, 15, 60):
        frame = windows(df, feats, minutes)
        parts = {
            name: frame[(frame.index >= start) & (frame.index < end)]
            for name, (start, end) in splits.items()
        }
        train = parts["train"]
        rules = build_rules(train)
        for name, fn in rules.items():
            for split in ("train", "val"):
                part = parts[split]
                row = score(np.asarray(fn(part)), part.up.to_numpy())
                row.update(H=minutes, signal=name, split=split, base_up=float(part.up.mean()))
                rows.append(row)
        table = pd.DataFrame([row for row in rows if row["H"] == minutes])
        pivot = table.pivot_table(index="signal", columns="split", values=["hit", "trades"])
        eligible = pivot[(pivot["hit"]["train"] > 0.5) & (pivot["trades"]["val"] >= 500)]
        best = eligible["hit"]["val"].idxmax()
        test = parts["test"]
        chosen = score(np.asarray(rules[best](test)), test.up.to_numpy())
        chosen.update(H=minutes, signal=best, split="TEST_selected", base_up=float(test.up.mean()))
        rows.append(chosen)
        for name, fn in rules.items():
            row = score(np.asarray(fn(test)), test.up.to_numpy())
            row.update(H=minutes, signal=name, split="test_posthoc", base_up=float(test.up.mean()))
            rows.append(row)
    return pd.DataFrame(rows)
