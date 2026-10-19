"""Experimental maker paper test.

Post a hypothetical resting bid, shaded by a directional signal, and mark it
filled only when a later public prices-history print trades through the limit.
Nothing is sent to an exchange.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aroonbot.polymarket import floor_window, last_at_or_before, prints_between
from aroonbot.research import attach_features, window_frame
from aroonbot.signals import SIGNAL_NEEDS, as_direction, features, library

ASSUMPTIONS = [
    "Paper only. No order is sent to Polymarket.",
    "The order is a buy of the token the signal favors.",
    "open_print shades that token's last public print at or before the open by `shade` dollars.",
    "half posts the bid at 0.50 minus `shade`, regardless of the print.",
    "If the limit is at or above the reference print, the order would cross and is not counted as a maker fill.",
    "A resting bid fills only when a later prices-history print on that same token, "
    "after the open and before the window end, is at or below the limit.",
    "The hypothetical fill price is the limit. prices-history is not the order book.",
    "Prints at or after the window end are ignored, so a 0 or 1 resolution print is not a fill.",
    "Settlement uses resolved outcomePrices of 0 or 1. Unresolved windows have no PnL.",
    "The taker fee is not charged. The maker rebate defaults to 0 and is never assumed.",
    "Unfilled orders are left out of the per-filled-share average.",
]


def maker_limit(reference: float, shade: float, anchor: str) -> float:
    if shade < 0 or shade > 0.25:
        raise ValueError("shade must be between 0 and 0.25")
    if anchor == "open_print":
        return float(reference - shade)
    if anchor == "half":
        return float(0.50 - shade)
    raise ValueError("anchor must be open_print or half")


def evaluate_order(
    *,
    window_start: pd.Timestamp,
    minutes: int,
    direction: int,
    rsi: float | None,
    market: dict,
    shade: float,
    anchor: str,
    rebate: float,
) -> dict:
    start_ts = int(pd.Timestamp(window_start).timestamp())
    end_ts = start_ts + minutes * 60
    token = "Up" if direction == 1 else "Down"
    base = {
        "window": pd.Timestamp(window_start).isoformat(),
        "minutes": minutes,
        "signal": "UP" if direction == 1 else "DOWN",
        "rsi": None if rsi is None or rsi != rsi else float(rsi),
        "token": token,
        "anchor": anchor,
        "shade": float(shade),
        "rebate": float(rebate),
        "slug": market.get("slug"),
        "title": market.get("title"),
    }
    if not market.get("ok"):
        return {
            **base,
            "status": "market_not_found",
            "filled": None,
            "pnl_per_share": None,
            "note": market.get("error"),
        }
    history = market.get("up_history") if token == "Up" else market.get("down_history")
    history = history or []
    reference = last_at_or_before(history, start_ts)
    note = None
    if reference is None and token == "Down":
        up_ref = last_at_or_before(market.get("up_history") or [], start_ts)
        if up_ref is not None:
            reference = 1.0 - up_ref
            note = "Down reference inferred as 1 minus the Up print; fill is not evaluated without Down prints."
    if reference is None:
        return {**base, "status": "no_reference_price", "filled": None, "pnl_per_share": None, "note": note}
    limit = maker_limit(reference, shade, anchor)
    base.update({"reference": float(reference), "limit": float(limit)})
    if not 0.01 <= limit <= 0.99:
        return {**base, "status": "limit_out_of_range", "filled": None, "pnl_per_share": None, "note": note}
    if limit >= reference - 1e-12:
        return {
            **base,
            "status": "marketable_not_counted",
            "filled": None,
            "pnl_per_share": None,
            "note": "Limit is at or above the open print, so this would not be a resting maker bid.",
        }
    if token == "Down" and not market.get("down_history"):
        return {
            **base,
            "status": "no_down_history",
            "filled": None,
            "pnl_per_share": None,
            "note": note or "No Down token prints, so a fill is not invented from the Up book.",
        }
    later = prints_between(history, start_ts, end_ts)
    prices = [float(point["p"]) for point in later]
    if not prices:
        return {
            **base,
            "status": "no_prints_after_open",
            "filled": None,
            "n_prints": 0,
            "pnl_per_share": None,
            "note": note,
        }
    min_print = float(min(prices))
    max_print = float(max(prices))
    filled = min_print <= limit + 1e-12
    settled = market.get("settled_up") if market.get("resolved") else None
    win = None
    pnl = None
    if filled and settled in (0.0, 1.0):
        win = (direction == 1 and settled == 1.0) or (direction == -1 and settled == 0.0)
        pnl = (1.0 if win else 0.0) - limit + rebate
    status = "filled" if filled else "resting_unfilled"
    return {
        **base,
        "status": status,
        "filled": filled,
        "fill_price": limit if filled else None,
        "min_print": min_print,
        "max_print": max_print,
        "n_prints": len(prices),
        "resolved": bool(market.get("resolved")),
        "settled_up": settled,
        "win": win,
        "pnl_per_share": pnl,
        "note": note,
    }


def plan_windows(df: pd.DataFrame, minutes: int, n_windows: int, now=None, signal: str = "rsi_mr_30_70") -> list[dict]:
    """Plan the last n completed windows. No network."""
    if n_windows < 1 or n_windows > 500:
        raise ValueError("n_windows must be between 1 and 500")
    if signal not in library():
        raise ValueError(f"unknown signal {signal}")
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    last = floor_window(now, minutes) - pd.Timedelta(minutes=minutes)
    starts = pd.date_range(last - pd.Timedelta(minutes=minutes * (n_windows - 1)), last, freq=f"{minutes}min")
    feats = features(df)
    frame = attach_features(window_frame(df, minutes), feats, SIGNAL_NEEDS[signal])
    fn = library()[signal]
    planned = []
    for ts in starts:
        if ts not in frame.index:
            planned.append(
                {
                    "window": pd.Timestamp(ts).isoformat(),
                    "ts": pd.Timestamp(ts),
                    "status": "no_feature",
                    "signal": None,
                }
            )
            continue
        direction = as_direction(np.asarray(fn(frame.loc[[ts]]))[0])
        rsi = float(frame.loc[ts, "rsi"]) if "rsi" in frame.columns else None
        if direction == 0:
            planned.append(
                {
                    "window": pd.Timestamp(ts).isoformat(),
                    "ts": pd.Timestamp(ts),
                    "status": "no_order",
                    "signal": 0,
                    "rsi": rsi,
                    "reason": "signal was neutral, so no bid is posted",
                }
            )
            continue
        planned.append(
            {
                "window": pd.Timestamp(ts).isoformat(),
                "ts": pd.Timestamp(ts),
                "status": "pending",
                "signal": direction,
                "rsi": rsi,
            }
        )
    return planned


def summarize_maker(rows: list[dict]) -> dict:
    resting = [row for row in rows if row.get("status") in ("filled", "resting_unfilled")]
    filled = [row for row in resting if row.get("filled")]
    settled_fills = [row["pnl_per_share"] for row in filled if row.get("pnl_per_share") is not None]
    posted_settled = []
    for row in resting:
        if row.get("status") == "filled" and row.get("pnl_per_share") is None:
            continue
        if row.get("status") == "resting_unfilled" and not row.get("resolved"):
            continue
        if row.get("status") == "filled":
            posted_settled.append(row["pnl_per_share"])
        elif row.get("resolved"):
            posted_settled.append(0.0)
    def _mean(values):
        return float(np.mean(values)) if values else None

    return {
        "orders_resting": len(resting),
        "filled": len(filled),
        "fill_rate": (len(filled) / len(resting)) if resting else None,
        "settled_fills": len(settled_fills),
        "avg_pnl_per_filled_share": _mean(settled_fills),
        "avg_pnl_per_posted_order_unfilled_as_zero": _mean(posted_settled),
        "marketable_skipped": sum(1 for row in rows if row.get("status") == "marketable_not_counted"),
        "neutrals": sum(1 for row in rows if row.get("status") == "no_order"),
    }


def evaluate_plan(
    plan: list[dict],
    markets: dict[str, dict],
    minutes: int,
    shade: float,
    anchor: str,
    rebate: float,
) -> dict:
    rows = []
    for item in plan:
        if item["status"] != "pending":
            rows.append(
                {
                    "window": item["window"],
                    "minutes": minutes,
                    "signal": {1: "UP", -1: "DOWN", 0: "NEUTRAL"}.get(item.get("signal"), None),
                    "rsi": item.get("rsi"),
                    "status": item["status"],
                    "filled": None,
                    "pnl_per_share": None,
                    "note": item.get("reason"),
                }
            )
            continue
        market = markets.get(item["window"]) or {"ok": False, "error": "not fetched"}
        rows.append(
            evaluate_order(
                window_start=item["ts"],
                minutes=minutes,
                direction=item["signal"],
                rsi=item.get("rsi"),
                market=market,
                shade=shade,
                anchor=anchor,
                rebate=rebate,
            )
        )
    return {"rows": rows, "summary": summarize_maker(rows), "assumptions": ASSUMPTIONS, "paper_only": True}
