import numpy as np
import pandas as pd

from aroonbot.agents import DOWN, NEUTRAL, UP, PaperExecutionAgent, RiskAgent, SignalAgent, SizerAgent
from aroonbot.backtest import run
from aroonbot.indicators import aroon


def test_aroon_uptrend():
    series = pd.Series(np.arange(30, dtype=float))
    up, down, osc = aroon(series, series, 14)
    assert up.iloc[-1] == 100 and down.iloc[-1] == 0 and osc.iloc[-1] == 100


def test_classify():
    agent = SignalAgent(14, 25)
    assert agent.classify(30) == UP
    assert agent.classify(-30) == DOWN
    assert agent.classify(10) == NEUTRAL
    assert agent.classify(25) == NEUTRAL


def test_sizer_cap():
    sizer = SizerAgent(0.02, 50)
    assert sizer.stake(1000) == 20 and sizer.stake(10000) == 50


def test_risk_limits():
    risk = RiskAgent(1000, 100, 3, 0.15)
    assert not risk.can_open("d", 3)
    risk.record("d", -100)
    assert not risk.can_open("d", 0) and risk.can_open("e", 0)
    risk.record("e", -60)
    assert risk.killed


def test_settle():
    execution = PaperExecutionAgent(0.5, 0.0)
    position = execution.open(UP, 10, None, None)
    assert execution.settle(position, 100, 101)[0] == 10
    assert execution.settle(position, 100, 99)[0] == -10


def test_no_live_execution_type():
    import aroonbot.agents as agents

    assert not any("live" in name.lower() for name in dir(agents))


def test_backtest_runs():
    index = pd.date_range("2026-01-01", periods=600, freq="1min", tz="UTC")
    price = 100 + np.cumsum(np.random.default_rng(0).normal(size=600))
    frame = pd.DataFrame({"open": price, "high": price + 0.5, "low": price - 0.5, "close": price}, index=index)
    result = run(frame, 15)
    assert result["windows"] == 40 and result["trades"] <= 40
