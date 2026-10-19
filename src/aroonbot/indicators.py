"""Technical indicators. Each value at bar t uses only bars at or before t."""

from __future__ import annotations

import numpy as np
import pandas as pd


def aroon(high: pd.Series, low: pd.Series, period: int = 14):
    """Aroon Up/Down over a window of period + 1 bars (standard definition)."""
    window = period + 1
    since_high = high.rolling(window).apply(lambda x: period - int(np.argmax(x)), raw=True)
    since_low = low.rolling(window).apply(lambda x: period - int(np.argmin(x)), raw=True)
    up = 100.0 * (period - since_high) / period
    down = 100.0 * (period - since_low) / period
    return up, down, up - down
