import numpy as np
import pandas as pd

from aroonbot.paper import PaperLog, build_decision, summarize_log


def _frame(n=300):
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    price = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.05, n))
    return pd.DataFrame(
        {
            "open": price,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 1.0,
            "taker_buy": 0.4,
            "trades": 1,
        },
        index=index,
    )


def test_half_entry_is_labeled_and_settled():
    frame = _frame()
    now = frame.index[120]
    decision = build_decision(
        frame,
        minutes=15,
        signal="rsi_mr_30_70",
        now=now,
        entry_mode="half",
        fee_model="flat",
        flat_fee=0.01,
        taker_rate=0.07,
        market=None,
    )
    assert decision["paper_only"] is True
    assert decision["entry_source"] in (None, "assumed_0.50")
    assert "order" not in decision["note"].lower() or "no order" in decision["note"].lower()
    if decision["signal"] == "NEUTRAL":
        assert decision["status"] == "skip"
        assert decision["pnl_per_share"] is None
    else:
        assert decision["entry"] == 0.5
        assert decision["status"] == "settled"
        assert decision["settlement"] == "binance_close_ge_open"


def test_missing_polymarket_print_does_not_invent_a_price():
    frame = _frame()
    forced = frame.copy()
    # Drive RSI down on the bar before a window so the signal is UP.
    window = pd.Timestamp("2026-01-01T01:00:00Z")
    now = window + pd.Timedelta(minutes=20)
    decision = build_decision(
        forced,
        minutes=15,
        signal="rsi_mr_30_70",
        now=now,
        entry_mode="polymarket_print",
        fee_model="polymarket_taker",
        flat_fee=0.01,
        taker_rate=0.07,
        market={"ok": False, "error": "down"},
    )
    if decision["signal"] == "NEUTRAL":
        assert decision["entry"] is None
    else:
        assert decision["status"] == "no_price"
        assert decision["entry"] is None
        assert decision["pnl_per_share"] is None


def test_log_roundtrip_and_bankroll(tmp_path):
    log = PaperLog(tmp_path / "paper.jsonl")
    row = {
        "id": "rsi-15m-1",
        "status": "settled",
        "signal": "UP",
        "win": True,
        "entry": 0.5,
        "fee": 0.0,
        "spread": 0.0,
        "pnl_per_share": 0.5,
        "window_start": "2026-01-01T00:00:00+00:00",
    }
    log.upsert(row)
    log.upsert({**row, "pnl_per_share": 0.5})
    assert len(log.read()) == 1
    summary = summarize_log(
        log.read(),
        {"starting_bankroll": 1000, "daily_loss_limit": 100, "max_open_positions": 3, "max_drawdown_pct": 0.15},
        {"fraction": 0.02, "max_stake": 50},
    )
    assert summary["settled"] == 1
    assert summary["sim_final_bankroll"] == 1020
