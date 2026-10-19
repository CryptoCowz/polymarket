import numpy as np
import pandas as pd

from aroonbot.indicators import aroon
from aroonbot.research import score, windows
from aroonbot.signals import fast_aroon_osc, features, library


def mk(n=4000, seed=1):
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    price = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 1e-3, n)))
    return pd.DataFrame(
        {"open": price, "high": price * 1.0005, "low": price * 0.9995, "close": price, "volume": 1.0, "taker_buy": 0.5},
        index=index,
    )


def test_fast_aroon_matches_reference():
    frame = mk(300)
    fast = fast_aroon_osc(frame.high, frame.low)
    _, _, slow = aroon(frame.high, frame.low)
    assert np.allclose(fast.dropna(), slow.dropna())


def test_no_lookahead():
    frame = mk()
    first = features(frame)
    bumped = frame.copy()
    bumped.iloc[-1, :4] *= 2
    second = features(bumped)
    assert first.iloc[:-1].equals(second.iloc[:-1])


def test_windows_use_prior_bar():
    frame = mk()
    feats = features(frame)
    sample = windows(frame, feats, 60)
    ts = sample.index[0]
    assert sample.loc[ts, "ret_1"] == feats.shift(1).loc[ts, "ret_1"]


def test_library_shapes_and_no_ensemble_refit():
    frame = mk()
    feats = features(frame)
    rules = library()
    assert "ensemble_logit_m0.05" not in rules
    assert "rsi_mr_30_70" in rules
    for name, fn in rules.items():
        assert len(fn(feats)) == len(feats), name


def test_score_breakeven():
    result = score(np.array([1, 1, -1, -1]), np.array([1, 0, 0, 0]))
    assert result["trades"] == 4
    assert abs(result["hit"] - 0.75) < 1e-9
    assert abs(result["pnl_sh_1c"] - 0.24) < 1e-9
