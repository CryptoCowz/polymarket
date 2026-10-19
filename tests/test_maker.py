import pandas as pd

from aroonbot.maker import evaluate_order, maker_limit, summarize_maker
from aroonbot.polymarket import taker_fee


def _market(start_ts, up, down, settled=1.0):
    return {
        "ok": True,
        "resolved": True,
        "settled_up": settled,
        "slug": "btc-updown-15m-test",
        "title": "test",
        "up_history": up,
        "down_history": down,
    }


def test_taker_fee_at_half():
    assert taker_fee(0.5) == 0.0175


def test_open_print_shade():
    assert maker_limit(0.53, 0.02, "open_print") == 0.51
    assert maker_limit(0.53, 0.02, "half") == 0.48


def test_fill_uses_later_print_not_resolution():
    start = pd.Timestamp("2026-10-01T00:00:00Z")
    start_ts = int(start.timestamp())
    end_ts = start_ts + 15 * 60
    market = _market(
        start_ts,
        up=[
            {"t": start_ts - 10, "p": 0.53},
            {"t": start_ts + 30, "p": 0.50},
            {"t": end_ts, "p": 0.01},
        ],
        down=[],
    )
    row = evaluate_order(
        window_start=start,
        minutes=15,
        direction=1,
        rsi=22.0,
        market=market,
        shade=0.02,
        anchor="open_print",
        rebate=0.0,
    )
    assert row["status"] == "filled"
    assert row["limit"] == 0.51
    assert row["pnl_per_share"] == 1 - 0.51


def test_price_that_never_trades_through_is_unfilled():
    start = pd.Timestamp("2026-10-01T00:15:00Z")
    start_ts = int(start.timestamp())
    market = _market(
        start_ts,
        up=[{"t": start_ts - 5, "p": 0.53}, {"t": start_ts + 20, "p": 0.52}],
        down=[],
        settled=0.0,
    )
    row = evaluate_order(
        window_start=start,
        minutes=15,
        direction=1,
        rsi=20,
        market=market,
        shade=0.02,
        anchor="open_print",
        rebate=0.0,
    )
    assert row["status"] == "resting_unfilled"
    assert row["filled"] is False
    assert row["pnl_per_share"] is None


def test_marketable_bid_is_not_a_maker_fill():
    start = pd.Timestamp("2026-10-01T00:30:00Z")
    start_ts = int(start.timestamp())
    market = _market(
        start_ts,
        up=[{"t": start_ts - 5, "p": 0.40}, {"t": start_ts + 10, "p": 0.39}],
        down=[],
    )
    row = evaluate_order(
        window_start=start,
        minutes=15,
        direction=1,
        rsi=20,
        market=market,
        shade=0.0,
        anchor="half",
        rebate=0.0,
    )
    assert row["status"] == "marketable_not_counted"
    assert row["pnl_per_share"] is None


def test_summary_keeps_unfilled_out_of_the_fill_average():
    rows = [
        {"status": "filled", "filled": True, "pnl_per_share": 0.2, "resolved": True},
        {"status": "resting_unfilled", "filled": False, "pnl_per_share": None, "resolved": True},
        {"status": "no_order"},
    ]
    summary = summarize_maker(rows)
    assert summary["filled"] == 1
    assert summary["orders_resting"] == 2
    assert summary["avg_pnl_per_filled_share"] == 0.2
    assert summary["avg_pnl_per_posted_order_unfilled_as_zero"] == 0.1
    assert summary["neutrals"] == 1
