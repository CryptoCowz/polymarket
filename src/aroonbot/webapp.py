"""Local web UI. Every route is paper or read-only public data."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aroonbot import __version__
from aroonbot.backtest import prediction_frame, signal_backtest
from aroonbot.config import load_config
from aroonbot.data import load_klines
from aroonbot.maker import ASSUMPTIONS, evaluate_plan, plan_windows
from aroonbot.paper import PaperLog, build_decision, settle_row, signals_at, summarize_log, window_prices
from aroonbot.polymarket import PublicPolymarket, floor_window, last_at_or_before, taker_fee
from aroonbot.signals import describe, family, library
from aroonbot.study import primary_pm, study_summary

PAPER = (
    "Paper and simulation only. This process does not place orders, "
    "create wallets, or use private keys."
)
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="BTC Up/Down Lab", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _clean(value):
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if np.isnan(number) or np.isinf(number):
            return None
        return number
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _minutes(minutes: int) -> int:
    if minutes not in (5, 15, 60):
        raise ValueError("minutes must be 5, 15, or 60")
    return minutes


def _range(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    date_only_end = len(end) <= 10
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")
    if date_only_end:
        end_ts = end_ts + pd.Timedelta(days=1)
    if end_ts <= start_ts:
        raise ValueError("end must be after start")
    if end_ts - start_ts > pd.Timedelta(days=120):
        raise ValueError("The web backtest is capped at 120 days. Use scripts/backtest.py for a longer run.")
    return start_ts, end_ts


def _fee(entry: float, fee_model: str, flat_fee: float, rate: float) -> float:
    if not 0.0 < entry < 1.0:
        raise ValueError("entry must be between 0 and 1")
    if fee_model == "polymarket_taker":
        return taker_fee(entry, rate)
    if fee_model == "flat":
        if flat_fee < 0 or flat_fee >= 1:
            raise ValueError("flat fee must be in [0, 1)")
        return float(flat_fee)
    raise ValueError("fee_model must be flat or polymarket_taker")


def _paper_log() -> PaperLog:
    return PaperLog("data/paper_log.jsonl")


def _maker_path() -> Path:
    return Path("data/maker_log.jsonl")


@app.exception_handler(ValueError)
async def _bad_request(_request, exc: ValueError):
    return JSONResponse({"error": str(exc), "paper_only": True}, status_code=400)


@app.exception_handler(RuntimeError)
async def _upstream(_request, exc: RuntimeError):
    return JSONResponse({"error": str(exc), "paper_only": True}, status_code=502)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.svg")
def favicon():
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        "<rect width='32' height='32' rx='4' fill='#7d2424'/>"
        "<text x='16' y='22' text-anchor='middle' font-size='14' fill='#fff8ee' "
        "font-family='Georgia'>P</text></svg>"
    )
    return Response(svg, media_type="image/svg+xml")


@app.get("/api/health")
def health():
    cfg = load_config()
    return {"ok": True, "paper_only": True, "mode": cfg["mode"], "version": __version__}


@app.get("/api/meta")
def meta():
    today = pd.Timestamp.now(tz="UTC").floor("D")
    signals = [
        {"id": name, "label": describe(name), "family": family(name)}
        for name in library()
    ]
    return {
        "paper_only": True,
        "disclaimer": PAPER,
        "signals": signals,
        "windows": [5, 15, 60],
        "suggested_start": str((today - pd.Timedelta(days=14)).date()),
        "suggested_end": str(today.date()),
        "default_signal": "rsi_mr_30_70",
        "maker_assumptions": ASSUMPTIONS,
    }


@app.get("/api/summary")
def summary():
    payload = study_summary()
    payload["disclaimer"] = PAPER
    return _clean(payload)


@app.get("/api/leaderboard")
def get_leaderboard():
    from aroonbot.study import leaderboard

    payload = leaderboard()
    payload["paper_only"] = True
    payload["disclaimer"] = PAPER
    return _clean(payload)


@app.get("/api/pm-check")
def get_pm_check():
    from aroonbot.study import pm_rows

    return {
        "paper_only": True,
        "disclaimer": PAPER,
        "note": (
            "These rows are the committed 2026 Polymarket price check "
            "(research/results/pm_check.csv). They are not recomputed when you open this page. "
            "Primary rows use the last public print at or before the window open and no extra spread."
        ),
        "rows": pm_rows(),
    }


class BacktestIn(BaseModel):
    signal: str
    minutes: int
    start: str
    end: str
    entry: float = 0.5
    fee_model: str = "flat"
    flat_fee: float = 0.01
    spread: float = 0.0
    taker_fee_rate: float = 0.07


@app.post("/api/backtest")
def post_backtest(body: BacktestIn):
    minutes = _minutes(body.minutes)
    if body.spread < 0 or body.spread > 0.2:
        raise ValueError("spread must be between 0 and 0.2")
    start, end = _range(body.start, body.end)
    fee = _fee(body.entry, body.fee_model, body.flat_fee, body.taker_fee_rate)
    cfg = load_config()
    frame = load_klines(start, end, symbol=cfg.get("symbol", "BTCUSDT"))
    result = signal_backtest(
        frame,
        body.signal,
        minutes=minutes,
        entry=body.entry,
        fee=fee,
        spread=body.spread,
        eval_start=start,
        eval_end=end,
        cfg_risk=cfg.get("risk"),
        cfg_size=cfg.get("sizing"),
    )
    result["fee_model"] = body.fee_model
    result["taker_fee_rate"] = body.taker_fee_rate if body.fee_model == "polymarket_taker" else None
    result["data_first"] = frame.index.min().isoformat()
    result["data_last"] = frame.index.max().isoformat()
    result["eval_start"] = start.isoformat()
    result["eval_end"] = end.isoformat()
    result["disclaimer"] = PAPER
    published = [row for row in primary_pm() if row["minutes"] == minutes]
    result["published_polymarket_check"] = published[0] if published else None
    result["published_polymarket_note"] = (
        "This is the committed 2026 study, not the date range of the run above."
    )
    return _clean(result)


class CompareIn(BaseModel):
    signal: str
    minutes: int
    start: str
    end: str
    max_markets: int = 12
    spread: float = 0.0
    taker_fee_rate: float = 0.07


@app.post("/api/pm-compare")
def post_pm_compare(body: CompareIn):
    minutes = _minutes(body.minutes)
    if not 1 <= body.max_markets <= 20:
        raise ValueError("max_markets must be between 1 and 20")
    start, end = _range(body.start, body.end)
    cfg = load_config()
    frame = load_klines(start, end, symbol=cfg.get("symbol", "BTCUSDT"))
    predicted = prediction_frame(frame, body.signal, minutes, start, end)
    fired = predicted[predicted.pred != 0]
    if fired.empty:
        return {"paper_only": True, "rows": [], "summary": None, "note": "The signal did not fire in this range."}
    sample = fired.tail(body.max_markets)
    def one(ts, direction):
        market = PublicPolymarket().window(ts, minutes)
        return ts, int(direction), market

    rows = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(one, ts, row.pred) for ts, row in sample.iterrows()]
        for future in as_completed(futures):
            ts, direction, market = future.result()
            rows.append(_compare_row(ts, direction, market, body.spread, body.taker_fee_rate))
    rows.sort(key=lambda row: row["window"])
    priced = [row for row in rows if row.get("cost") is not None and row.get("pnl_per_share") is not None]
    summary = None
    if priced:
        pnl = np.array([row["pnl_per_share"] for row in priced], dtype=float)
        summary = {
            "n": len(priced),
            "hit": float(np.mean([row["win"] for row in priced])),
            "avg_cost": float(np.mean([row["cost"] for row in priced])),
            "avg_pnl_per_share": float(pnl.mean()),
            "se": float(pnl.std(ddof=1) / np.sqrt(len(pnl))) if len(pnl) > 1 else None,
        }
    return _clean(
        {
            "paper_only": True,
            "disclaimer": PAPER,
            "note": (
                f"Read-only sample of the {len(sample)} most recent fired windows in this range "
                f"({len(fired)} fired in total). Missing markets are omitted. "
                f"PnL uses the taker fee {body.taker_fee_rate:.2f}·p·(1−p) plus the requested spread. "
                "This is not the published 2026 study."
            ),
            "fired_in_range": int(len(fired)),
            "fetched": len(rows),
            "summary": summary,
            "rows": rows,
        }
    )


def _compare_row(ts, direction: int, market: dict, spread: float, rate: float) -> dict:
    start_ts = int(pd.Timestamp(ts).timestamp())
    token = "Up" if direction == 1 else "Down"
    history = (market.get("up_history") if token == "Up" else market.get("down_history")) or []
    price = last_at_or_before(history, start_ts) if market.get("ok") else None
    source = "token_print"
    if price is None and token == "Down" and market.get("ok"):
        up = last_at_or_before(market.get("up_history") or [], start_ts)
        if up is not None:
            price = 1.0 - up
            source = "inferred_one_minus_up"
    row = {
        "window": pd.Timestamp(ts).isoformat(),
        "signal": "UP" if direction == 1 else "DOWN",
        "slug": market.get("slug"),
        "token": token,
        "cost": price,
        "price_source": source if price is not None else None,
        "resolved": bool(market.get("resolved")),
        "win": None,
        "pnl_per_share": None,
        "error": market.get("error"),
    }
    if price is None or not market.get("resolved"):
        return row
    settled = market.get("settled_up")
    win = (direction == 1 and settled == 1.0) or (direction == -1 and settled == 0.0)
    fee = taker_fee(price, rate)
    row.update(
        {
            "win": bool(win),
            "fee": fee,
            "pnl_per_share": (1.0 if win else 0.0) - price - fee - spread,
        }
    )
    return row


class TickIn(BaseModel):
    minutes: int = 15
    signal: str = "rsi_mr_30_70"
    entry_mode: str = "polymarket_print"
    fee_model: str = "polymarket_taker"
    flat_fee: float = 0.01


def _recent_klines(hours: int = 72):
    cfg = load_config()
    now = pd.Timestamp.now(tz="UTC")
    return load_klines(
        now - pd.Timedelta(hours=hours),
        now + pd.Timedelta(minutes=1),
        symbol=cfg.get("symbol", "BTCUSDT"),
        warmup=pd.Timedelta(0),
    )


def _refresh(log: PaperLog, df: pd.DataFrame) -> list[dict]:
    rows = log.read()
    now = pd.Timestamp.now(tz="UTC")
    changed = False
    for i, row in enumerate(rows):
        if row.get("status") != "open":
            continue
        start = pd.Timestamp(row["window_start"])
        minutes = int(row["minutes"])
        if now < start + pd.Timedelta(minutes=minutes):
            continue
        prices = window_prices(df, start, minutes)
        if prices is None:
            continue
        rows[i] = settle_row(row, prices, None)
        changed = True
    if changed:
        log.write(rows)
    return rows


@app.get("/api/paper/snapshot")
def paper_snapshot(minutes: int = 15):
    minutes = _minutes(minutes)
    now = pd.Timestamp.now(tz="UTC")
    df = _recent_klines()
    start = floor_window(now, minutes)
    end = start + pd.Timedelta(minutes=minutes)
    reading = signals_at(df, start)
    closed = df[df.index < now.floor("min")]
    spark = [float(value) for value in closed["close"].tail(120).tolist()]
    return _clean(
        {
            "paper_only": True,
            "disclaimer": PAPER,
            "now": now.isoformat(),
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "seconds_left": max(0, int((end - now).total_seconds())),
            "btc": reading["btc_close"],
            "rsi": reading["rsi"],
            "aroon": reading["aroon"],
            "bb_z": reading["bb_z"],
            "feature_asof": reading["asof"],
            "signals": [
                {"id": name, "label": describe(name), "side": reading["signals"].get(name)}
                for name in library()
            ],
            "spark": spark,
        }
    )


@app.get("/api/paper/log")
def paper_log():
    cfg = load_config()
    log = _paper_log()
    try:
        df = _recent_klines()
        rows = _refresh(log, df)
    except Exception:
        rows = log.read()
    return {
        "paper_only": True,
        "disclaimer": PAPER,
        "summary": _clean(summarize_log(rows, cfg.get("risk"), cfg.get("sizing"))),
        "rows": rows,
    }


@app.post("/api/paper/tick")
def paper_tick(body: TickIn):
    minutes = _minutes(body.minutes)
    if body.signal not in library():
        raise ValueError(f"unknown signal {body.signal}")
    cfg = load_config()
    now = pd.Timestamp.now(tz="UTC")
    df = _recent_klines()
    market = None
    if body.entry_mode == "polymarket_print":
        try:
            market = PublicPolymarket().window(floor_window(now, minutes), minutes)
        except Exception as exc:
            market = {"ok": False, "error": str(exc)}
    decision = build_decision(
        df,
        minutes=minutes,
        signal=body.signal,
        now=now,
        entry_mode=body.entry_mode,
        fee_model=body.fee_model,
        flat_fee=body.flat_fee,
        taker_rate=float(cfg.get("polymarket", {}).get("taker_fee_rate", 0.07)),
        market=market,
    )
    log = _paper_log()
    rows = log.upsert(decision)
    rows = _refresh(log, df)
    return _clean(
        {
            "paper_only": True,
            "disclaimer": PAPER,
            "decision": decision,
            "summary": summarize_log(rows, cfg.get("risk"), cfg.get("sizing")),
            "rows": rows,
        }
    )


class MakerIn(BaseModel):
    minutes: int = 15
    n_windows: int = Field(default=16, ge=1, le=48)
    shade: float = 0.02
    anchor: str = "open_print"
    rebate: float = 0.0
    signal: str = "rsi_mr_30_70"
    max_markets: int = Field(default=16, ge=1, le=24)


@app.post("/api/maker/replay")
def maker_replay(body: MakerIn):
    minutes = _minutes(body.minutes)
    if body.anchor not in ("open_print", "half"):
        raise ValueError("anchor must be open_print or half")
    if abs(body.rebate) > 0.05:
        raise ValueError("rebate is capped at 5¢ for this paper test")
    cfg = load_config()
    now = pd.Timestamp.now(tz="UTC")
    lookback = pd.Timedelta(minutes=minutes * body.n_windows + 60)
    df = load_klines(
        now - lookback,
        now + pd.Timedelta(minutes=1),
        symbol=cfg.get("symbol", "BTCUSDT"),
        warmup=pd.Timedelta(days=3),
    )
    plan = plan_windows(df, minutes, body.n_windows, now=now, signal=body.signal)
    pending = [item for item in plan if item["status"] == "pending"]
    skipped = 0
    if len(pending) > body.max_markets:
        skipped = len(pending) - body.max_markets
        keep = {item["window"] for item in pending[-body.max_markets :]}
        for item in plan:
            if item["status"] == "pending" and item["window"] not in keep:
                item["status"] = "capped"
                item["reason"] = "older than the fetch cap"
    markets: dict[str, dict] = {}

    def fetch(item):
        try:
            return item["window"], PublicPolymarket().window(item["ts"], minutes)
        except Exception as exc:
            return item["window"], {"ok": False, "error": str(exc)}

    targets = [item for item in plan if item["status"] == "pending"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for window, market in pool.map(fetch, targets):
            markets[window] = market
    result = evaluate_plan(plan, markets, minutes, body.shade, body.anchor, body.rebate)
    result.update(
        {
            "signal": body.signal,
            "minutes": minutes,
            "shade": body.shade,
            "anchor": body.anchor,
            "rebate": body.rebate,
            "fires_skipped_by_cap": skipped,
            "disclaimer": PAPER,
        }
    )
    path = _maker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_at": now.isoformat(),
        "signal": body.signal,
        "minutes": minutes,
        "shade": body.shade,
        "anchor": body.anchor,
        "rebate": body.rebate,
        "summary": result["summary"],
        "rows": result["rows"],
    }
    with path.open("a") as handle:
        handle.write(json.dumps(_clean(record)) + "\n")
    return _clean(result)


@app.get("/api/maker/log")
def maker_log():
    path = _maker_path()
    if not path.exists():
        return {"paper_only": True, "runs": [], "disclaimer": PAPER}
    runs = []
    for line in path.read_text().splitlines():
        if line.strip():
            runs.append(json.loads(line))
    latest = runs[-1] if runs else None
    history = [
        {
            "run_at": run.get("run_at"),
            "signal": run.get("signal"),
            "minutes": run.get("minutes"),
            "shade": run.get("shade"),
            "anchor": run.get("anchor"),
            "summary": run.get("summary"),
        }
        for run in runs[-12:]
    ]
    return {"paper_only": True, "disclaimer": PAPER, "latest": latest, "history": history}


def main():
    import uvicorn

    load_config()
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("aroonbot.webapp:app", host="0.0.0.0", port=port, reload=False)
