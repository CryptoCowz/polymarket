"""Read the committed study artifacts and restate the selection rule.

Performance figures returned here are computed from those files. They are not
typed in by hand.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from aroonbot.config import artifacts_dir
from aroonbot.signals import describe, family

PRIMARY_PM_PRICE = {5: "p_up_before", 15: "p_up_before", 60: "p_up_0s"}


def bonferroni_z(n_trials: int, alpha: float = 0.05) -> float:
    if n_trials < 1:
        raise ValueError("n_trials must be positive")
    return float(norm.ppf(1 - alpha / n_trials))


def _f(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if pd.isna(value):
        return None
    return float(value)


def _i(value) -> int:
    return int(value)


def load_research(path: Path | None = None) -> pd.DataFrame:
    path = path or artifacts_dir() / "research_results.csv"
    frame = pd.read_csv(path)
    frame["H"] = frame["H"].astype(int)
    return frame


def load_pm_check(path: Path | None = None) -> pd.DataFrame:
    path = path or artifacts_dir() / "pm_check.csv"
    return pd.read_csv(path)


def _row_metrics(row: pd.Series) -> dict:
    return {
        "signal": str(row["signal"]),
        "description": describe(str(row["signal"])),
        "family": family(str(row["signal"])),
        "minutes": _i(row["H"]),
        "split": str(row["split"]),
        "trades": _i(row["trades"]),
        "hit": _f(row["hit"]),
        "z_vs_50": _f(row["z_vs_50"]),
        "pnl_1c": _f(row["pnl_sh_1c"]),
        "z_breakeven_1c": _f(row["z_vs_breakeven_1c"]),
        "pnl_3c": _f(row["pnl_sh_3c"]),
        "z_breakeven_3c": _f(row["z_vs_breakeven_3c"]),
        "base_up": _f(row["base_up"]),
    }


def leaderboard(frame: pd.DataFrame | None = None, alpha: float = 0.05) -> dict:
    frame = load_research() if frame is None else frame
    validation = frame[frame.split == "val"]
    n_variants = int(len(validation))
    threshold = bonferroni_z(n_variants, alpha)
    selected = []
    validation_rows = []
    posthoc_rows = []
    for minutes, group in frame.groupby("H"):
        train = group[group.split == "train"].set_index("signal")
        val = group[group.split == "val"].set_index("signal")
        eligible = []
        for name in val.index:
            if name not in train.index:
                continue
            train_hit = train.loc[name, "hit"]
            val_trades = val.loc[name, "trades"]
            val_hit = val.loc[name, "hit"]
            if pd.notna(train_hit) and train_hit > 0.5 and val_trades >= 500 and pd.notna(val_hit):
                eligible.append(name)
        best = max(eligible, key=lambda name: float(val.loc[name, "hit"])) if eligible else None
        test_rows = group[group.split == "TEST_selected"]
        chosen = test_rows[test_rows.signal == best]
        if best is not None and len(chosen) == 1:
            metrics = _row_metrics(chosen.iloc[0])
            val_z = _f(val.loc[best, "z_vs_50"])
            metrics.update(
                {
                    "train_hit": _f(train.loc[best, "hit"]),
                    "train_trades": _i(train.loc[best, "trades"]),
                    "val_hit": _f(val.loc[best, "hit"]),
                    "val_trades": _i(val.loc[best, "trades"]),
                    "val_z": val_z,
                    "passes_bonferroni": bool(val_z is not None and val_z >= threshold),
                }
            )
            selected.append(metrics)
        for name, row in val.iterrows():
            labeled = row.copy()
            labeled["signal"] = name
            item = _row_metrics(labeled)
            train_hit = _f(train.loc[name, "hit"]) if name in train.index else None
            item.update(
                {
                    "train_hit": train_hit,
                    "train_trades": _i(train.loc[name, "trades"]) if name in train.index else 0,
                    "passes_bonferroni": bool(
                        item["z_vs_50"] is not None and item["z_vs_50"] >= threshold
                    ),
                    "selected": name == best,
                    "eligible": name in eligible,
                }
            )
            validation_rows.append(item)
        for _, row in group[group.split == "test_posthoc"].iterrows():
            item = _row_metrics(row)
            item["selected"] = row["signal"] == best
            posthoc_rows.append(item)
    selected.sort(key=lambda row: row["minutes"])
    validation_rows.sort(key=lambda row: (-(row["hit"] or -1), row["minutes"], row["signal"]))
    posthoc_rows.sort(key=lambda row: (-(row["hit"] or -1), row["minutes"]))
    return {
        "n_validation_variants": n_variants,
        "alpha": alpha,
        "bonferroni_z": threshold,
        "selection_rule": (
            "For each horizon, choose the signal with the highest 2025 validation hit rate "
            "among signals whose 2022–2024 train hit rate is above 50% and that have at least "
            "500 validation trades. That signal is then scored once on 2026."
        ),
        "multiple_testing_note": (
            f"One-sided Bonferroni z for {n_variants} validation variants at p = {alpha} "
            f"is {threshold:.2f}. A validation result below that line does not clear the screen, "
            "even if the selection rule still picks it as the best eligible signal. "
            "test_posthoc rows were computed after the test period was visible and are not a clean test."
        ),
        "selected": selected,
        "validation": validation_rows,
        "posthoc": posthoc_rows,
    }


def pm_rows(frame: pd.DataFrame | None = None) -> list[dict]:
    frame = load_pm_check() if frame is None else frame
    rows = []
    for record in frame.to_dict(orient="records"):
        minutes = int(record["H"])
        price = str(record["price"])
        rows.append(
            {
                "minutes": minutes,
                "price": price,
                "extra_spread": float(record["extra_spread"]),
                "n_fire": int(record["n_fire"]),
                "hit": float(record["hit"]),
                "avg_cost": float(record["avg_cost"]),
                "avg_pnl_per_share": float(record["avg_pnl_sh"]),
                "se": float(record["se"]),
                "avg_p_up_when_up": float(record["avg_p_up_when_sigUP"]),
                "avg_p_up_when_down": float(record["avg_p_up_when_sigDOWN"]),
                "avg_p_up_control": float(record["avg_p_up_ctrl"]),
                "n_control": int(record["n_ctrl"]),
                "primary": price == PRIMARY_PM_PRICE.get(minutes) and float(record["extra_spread"]) == 0.0,
            }
        )
    return rows


def primary_pm(rows: list[dict] | None = None) -> list[dict]:
    rows = pm_rows() if rows is None else rows
    return [row for row in rows if row["primary"]]


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _cents(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.2f}¢"


def study_summary() -> dict:
    board = leaderboard()
    prices = primary_pm()
    pm_negative = bool(prices) and all(row["avg_pnl_per_share"] < 0 for row in prices)
    test_above_coin = bool(board["selected"]) and all(row["hit"] > 0.5 for row in board["selected"])
    if test_above_coin and pm_negative:
        headline = (
            "On Binance prices, the selected rules beat a coin flip on the untouched 2026 test. "
            "On the actual Polymarket prints from that same study, every horizon loses money "
            "per share after the taker fee."
        )
    elif pm_negative:
        headline = (
            "After real Polymarket prices and the taker fee, every published horizon has negative per-share PnL."
        )
    else:
        headline = "Figures below are computed from the committed study files."
    sentences = []
    for row in board["selected"]:
        screen = (
            "clears the validation Bonferroni screen"
            if row["passes_bonferroni"]
            else "does not clear the validation Bonferroni screen"
        )
        sentences.append(
            f"Untouched 2026 test, {row['minutes']}m {row['signal']}: hit {_pct(row['hit'])} "
            f"on {row['trades']:,} trades (z vs 50% = {row['z_vs_50']:.2f}). "
            f"At a $0.50 entry and a 1¢ fee that is {_cents(row['pnl_1c'])}/share, "
            f"and {_cents(row['pnl_3c'])}/share at a 3¢ fee. "
            f"Validation hit {_pct(row['val_hit'])} (z = {row['val_z']:.2f}) {screen}."
        )
    for row in prices:
        sentences.append(
            f"Real Polymarket {row['minutes']}m markets in the 2026 test, price column {row['price']}: "
            f"{row['n_fire']:,} fired windows, settlement hit {_pct(row['hit'])}, "
            f"average cost of the predicted side ${row['avg_cost']:.3f}. "
            f"After the taker fee, average PnL is {_cents(row['avg_pnl_per_share'])}/share "
            f"(SE {abs(row['se']) * 100:.2f}¢). "
            f"Up was priced at {row['avg_p_up_when_up']:.3f} when the signal said UP, "
            f"{row['avg_p_up_when_down']:.3f} when it said DOWN, and {row['avg_p_up_control']:.3f} "
            f"on {row['n_control']:,} control windows."
        )
    return {
        "paper_only": True,
        "splits": {
            "train": "2022-01-01 to 2025-01-01",
            "validation": "2025-01-01 to 2026-01-01",
            "test": "2026-01-01 to 2026-10-19",
        },
        "outcome": "Up if the window close is greater than or equal to the open.",
        "fee_note": "Polymarket taker fee in the price check is 0.07 * p * (1 - p) per share.",
        "selected": board["selected"],
        "bonferroni_z": board["bonferroni_z"],
        "n_validation_variants": board["n_validation_variants"],
        "polymarket_primary": prices,
        "headline": headline,
        "sentences": sentences,
        "source": "research/results/research_results.csv and research/results/pm_check.csv",
    }
