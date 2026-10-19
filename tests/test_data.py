import pandas as pd

from aroonbot.data import KlineStore, parse_kline_csv


def test_parse_microsecond_and_millisecond_timestamps():
    micro = b"1792281600000000,10,12,9,11,3,0,0,4,1.5,0,0\n"
    milli = b"1792281600000,10,12,9,11,3,0,0,4,1.5,0,0\n"
    for raw in (micro, milli):
        frame = parse_kline_csv(raw)
        assert frame.index[0] == pd.Timestamp("2026-10-18", tz="UTC")
        assert frame.close.iloc[0] == 11
        assert frame.taker_buy.iloc[0] == 1.5
        assert frame.trades.iloc[0] == 4


def test_store_uses_complete_months_and_slices(monkeypatch, tmp_path):
    index = pd.date_range("2026-08-01", periods=180, freq="1min", tz="UTC")
    monthly = pd.DataFrame(
        {
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
            "taker_buy": 0.2,
            "trades": 1,
        },
        index=index,
    )
    store = KlineStore(tmp_path)
    calls = {"days": 0}

    def _monthly(year_month):
        return monthly if year_month == "2026-08" else None

    def _day(day, today, end):
        calls["days"] += 1
        raise AssertionError("complete month should not fall through to days")

    monkeypatch.setattr(store, "_monthly", _monthly)
    monkeypatch.setattr(store, "_day", _day)
    loaded = store.load("2026-08-01", "2026-08-01 02:00", warmup=pd.Timedelta(0))
    assert calls["days"] == 0
    assert loaded.index.min() >= pd.Timestamp("2026-08-01", tz="UTC")
    assert loaded.index.max() < pd.Timestamp("2026-08-01 02:00", tz="UTC")
    assert len(loaded) == 120
