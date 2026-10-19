"""Signal, risk, sizer, and simulated execution.

Execution is simulated. There is deliberately no live execution type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aroonbot.indicators import aroon

UP, DOWN, NEUTRAL = "UP", "DOWN", "NEUTRAL"


class SignalAgent:
    def __init__(self, period: int = 14, threshold: float = 25):
        self.period = period
        self.threshold = threshold

    def classify(self, osc: float) -> str:
        if osc != osc:
            return NEUTRAL
        if osc > self.threshold:
            return UP
        if osc < -self.threshold:
            return DOWN
        return NEUTRAL

    def signals(self, df):
        _, _, osc = aroon(df["high"], df["low"], self.period)
        return osc.map(self.classify), osc


@dataclass
class Position:
    side: str
    stake: float
    shares: float
    window_start: object
    window_end: object


@dataclass
class RiskAgent:
    starting_bankroll: float = 1000.0
    daily_loss_limit: float = 100.0
    max_open_positions: int = 3
    max_drawdown_pct: float = 0.15
    bankroll: float = field(init=False)
    peak: float = field(init=False)
    killed: bool = field(init=False, default=False)
    daily_pnl: dict = field(init=False, default_factory=dict)

    def __post_init__(self):
        self.bankroll = self.peak = self.starting_bankroll

    def can_open(self, day, open_count: int) -> bool:
        if self.killed:
            return False
        if open_count >= self.max_open_positions:
            return False
        if self.daily_pnl.get(day, 0.0) <= -self.daily_loss_limit:
            return False
        return True

    def record(self, day, pnl: float) -> None:
        self.bankroll += pnl
        self.daily_pnl[day] = self.daily_pnl.get(day, 0.0) + pnl
        self.peak = max(self.peak, self.bankroll)
        if self.bankroll <= self.peak * (1 - self.max_drawdown_pct):
            self.killed = True


class SizerAgent:
    def __init__(self, fraction: float = 0.02, max_stake: float = 50.0):
        self.fraction = fraction
        self.max_stake = max_stake

    def stake(self, bankroll: float) -> float:
        return max(0.0, min(bankroll * self.fraction, self.max_stake))


class PaperExecutionAgent:
    """Simulated fills only. There is deliberately no order-placement method."""

    def __init__(self, entry_price: float = 0.50, fee_per_share: float = 0.02):
        self.entry_price = entry_price
        self.fee = fee_per_share

    def open(self, side: str, stake: float, window_start, window_end) -> Position:
        shares = stake / (self.entry_price + self.fee)
        return Position(side, stake, shares, window_start, window_end)

    def settle(self, pos: Position, start_price: float, end_price: float):
        # Legacy Aroon study counted a tie as Down. The research harness uses >=.
        went_up = end_price > start_price
        win = (pos.side == UP and went_up) or (pos.side == DOWN and not went_up)
        pnl = (pos.shares * 1.0 if win else 0.0) - pos.stake
        return pnl, win
