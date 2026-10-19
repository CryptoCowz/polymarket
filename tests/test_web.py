import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from aroonbot.paper import PaperLog
from aroonbot.webapp import app


def _prices(n=3000):
    end = pd.Timestamp.now(tz="UTC").floor("min")
    index = pd.date_range(end - pd.Timedelta(minutes=n - 1), periods=n, freq="1min", tz="UTC")
    price = 100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0, 1e-3, n)))
    return pd.DataFrame(
        {
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price,
            "volume": 1.0,
            "taker_buy": 0.4,
            "trades": 1,
        },
        index=index,
    )


def test_pages_are_labeled_paper():
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    assert "PAPER / SIMULATION ONLY" in page.text
    assert "no orders" in page.text
    health = client.get("/api/health").json()
    assert health["mode"] == "paper"
    assert health["paper_only"] is True
    summary = client.get("/api/summary").json()
    assert summary["polymarket_primary"]
    assert all(row["avg_pnl_per_share"] < 0 for row in summary["polymarket_primary"])
    board = client.get("/api/leaderboard").json()
    assert board["n_validation_variants"] == 81
    assert "test_posthoc" in board["multiple_testing_note"] or "not a clean test" in board["multiple_testing_note"]


class _OfflineMarket:
    def window(self, ts, minutes):
        return {"ok": False, "error": "offline test", "up_history": [], "down_history": [], "resolved": False}


def test_backtest_and_paper_routes_compute(monkeypatch, tmp_path):
    monkeypatch.setattr("aroonbot.webapp.load_klines", lambda *args, **kwargs: _prices())
    monkeypatch.setattr("aroonbot.webapp.PublicPolymarket", lambda *args, **kwargs: _OfflineMarket())
    monkeypatch.setattr("aroonbot.webapp._paper_log", lambda: PaperLog(tmp_path / "paper.jsonl"))
    monkeypatch.setattr("aroonbot.webapp._maker_path", lambda: tmp_path / "maker.jsonl")
    client = TestClient(app)
    today = pd.Timestamp.now(tz="UTC").date()
    start = str(today - pd.Timedelta(days=1))
    response = client.post(
        "/api/backtest",
        json={
            "signal": "rsi_mr_30_70",
            "minutes": 15,
            "start": start,
            "end": str(today),
            "entry": 0.5,
            "fee_model": "polymarket_taker",
            "flat_fee": 0.01,
            "spread": 0,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paper_only"] is True
    assert body["fee"] == 0.0175
    assert body["breakeven_hit_rate"] == 0.5 + 0.0175
    assert body["published_polymarket_check"]["avg_pnl_per_share"] < 0
    tick = client.post(
        "/api/paper/tick",
        json={"minutes": 15, "signal": "rsi_mr_30_70", "entry_mode": "half", "fee_model": "flat", "flat_fee": 0.01},
    )
    assert tick.status_code == 200, tick.text
    assert tick.json()["decision"]["paper_only"] is True
    snap = client.get("/api/paper/snapshot?minutes=15")
    assert snap.status_code == 200
    assert snap.json()["signals"]
    maker = client.post("/api/maker/replay", json={"minutes": 15, "n_windows": 4, "max_markets": 2, "shade": 0.02})
    assert maker.status_code == 200, maker.text
    assert maker.json()["paper_only"] is True
    assert maker.json()["assumptions"]


def test_live_config_is_rejected(tmp_path):
    from aroonbot.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text("mode: live\n")
    try:
        load_config(path)
    except SystemExit as exc:
        assert "paper" in str(exc)
    else:
        raise AssertionError("live mode was accepted")
