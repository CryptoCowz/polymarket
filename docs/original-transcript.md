HISTORICAL TRANSCRIPT. This is the original idea conversation. It discusses live
trading and contains placeholder private-key examples, not real keys. This
repository does not implement wallets, keys, or order placement. Live mode does
not exist.

---

# Grok shared conversation transcript

Source: https://x.com/i/grok/share/c2hhcmQtNA_9a7fac6b-204d-4d85-bb71-580b1f838362
Page title: "The X post showcases a trader's success... / Grok / X"
Transcribed read-only from the rendered page text (page innerText). Role markers (**USER** / **GROK**) were added by the transcriber; the page shows user prompts as right-aligned bubbles. Math (KaTeX) renders were duplicated in the raw text as broken fragments (rendered then raw LaTeX); these are left as extracted in the later sections and cleaned in the first section. Code blocks lose their fencing in extracted text, so some fences below are missing/ragged where the page used code boxes.

---

**USER:**
https://x.com/Dan1ro0/status/2111893686661402793

**GROK:**
- The X post showcases a trader's success using Grok Bot to develop a multi-agent Quant Trend system for Polymarket's BTC "Up or Down" prediction markets, achieving an average of $1,519 daily profit and +$268k total PnL over 177 days with repeated low-stake trades.
- Core strategy relies on Aroon indicators to identify fresh highs/lows and the Aroon Oscillator (Aroon Up minus Aroon Down) to gauge trend strength, triggering positions only on clear directional dominance while ignoring neutral periods.
- Accompanying video displays a dynamic "Grok Desk" dashboard with collaborating AI agents (Taker, Spotter, Kelly, Edge, Closer) managing live trades, featuring updating PnL charts, price action visuals, and signal readouts demonstrating real-time execution.

**USER:**
Can I build this with Grok?

**GROK:**
**Yes, you can build a similar system with my help (Grok).** The post describes a multi-agent setup using the Aroon indicator + Aroon Oscillator for directional bias on Polymarket's short-term BTC "Up or Down" markets (typically 5m/15m/hourly windows), with agents handling signal generation, sizing, execution, risk, etc.

I can help you design, code, backtest, and iterate on the core logic, a modular multi-agent architecture, data feeds, and integration with Polymarket's CLOB API. Many people already use Grok (and similar models) exactly this way to prototype quant strategies and bots. There are also open-source Polymarket BTC Up/Down bots and Python SDKs you can adapt.

**What I can help you build**
- **Aroon signal engine**: Exact formulas from the post
  - Aroon Up = 100 × (N − periods since high) / N
  - Aroon Down = 100 × (N − periods since low) / N
  - Aroon Oscillator = Aroon Up − Aroon Down
  - Rules for Up/Down bias and ignoring neutral periods when the oscillator is near zero.
- Multi-agent structure (e.g., Spotter for signals, Edge/Kelly for sizing, Taker/Closer for execution, Risk for limits) — either as coordinated Python modules, separate LLM-prompted agents, or a simple event-driven loop.
- Data pipeline: live BTC prices (Binance or similar WebSocket/REST), Polymarket market discovery and order-book data.
- Order placement, position tracking, and basic inventory management using official or community Polymarket Python clients.
- Backtesting / paper-trading framework, parameter sweeps (period N, oscillator thresholds), risk controls (max size, drawdown kill-switch, fees/slippage).
- Dashboard ideas or logging so you can monitor PnL, signals, and fills.

**Realistic constraints and warnings**
- Performance claims in these posts (and the many similar ones from the same account using different indicators) should be treated skeptically. Past results are not guarantees; edges on short-term prediction markets are competitive, thin at size, and eroded by fees, latency, and adverse selection.
You need a Polygon wallet funded with the appropriate collateral (USDC.e / pUSD), API credentials, and careful handling of private keys. I cannot run live trades, hold keys, or guarantee profitability.
Geo-restrictions and terms of service apply on Polymarket. Start with paper trading / dry-run mode.
Real edge usually comes from speed, accurate fair-value modeling relative to the order book, inventory management, and execution quality—not just a single classic indicator. Pure directional Aroon systems can work in strong trends but suffer in chop.
Computational and infrastructure needs: low-latency data + order placement matter for high-frequency repetition (the post mentions ~27 setups per hour).
How to get started right now

Tell me your preferred tech stack and level of ambition, for example:

“Write a clean Python class that computes Aroon + Oscillator on OHLCV data and emits Up/Down/Neutral signals.”
“Sketch a multi-agent architecture with roles matching the post (Spotter, Kelly, Edge, etc.) and show how they hand off.”
“Help me fetch current BTC Up/Down markets and order books via the Polymarket API.”
“Build a simple backtester that takes historical BTC candles + simulated Polymarket prices.”
Or share your current code / experience level and we’ll iterate from there.

I can generate working code snippets, explain every step, help debug, suggest improvements (e.g., combining Aroon with volatility filters or fair-value models), and keep everything modular so you stay in control.

Ready when you are—what part do you want to tackle first?


---

**USER:**
Walk me through building this step by step

**GROK:**

Yes — here’s a practical, sequential walkthrough to build a system inspired by the post: an Aroon-based directional signal on Polymarket’s short-term BTC “Up or Down” markets, organized as cooperating modules (agents).

This is educational. Real trading involves significant risk of loss, fees, slippage, latency competition, and possible geo-restrictions. Start in paper/dry-run mode. Never risk money you cannot afford to lose. The promotional PnL numbers in those posts should be treated with skepticism.

Step 0: Mindset and Prerequisites
Goal: Detect short-term BTC trend strength with Aroon → bias toward Up or Down outcome → size and place orders only when the signal is clear → manage risk and inventory.
You will need:
Python 3.11+
A Polygon wallet (EOA) funded with the collateral Polymarket uses (typically USDC.e → pUSD)
Basic comfort with APIs, WebSockets, and pandas
Key principle: Build modularly. Get the signal working offline first, then paper-trade, then tiny live size.
Step 1: Set Up Your Development Environment
bash
python -m venv venv
source venv/bin/activate   # or Windows equivalent
pip install pandas numpy pandas-ta requests websocket-client python-dotenv
# Official unified SDK (preferred in 2026)
pip install polymarket-client
# Optional but useful
pip install ccxt   # for easy BTC price data from Binance etc.

Create a .env file (never commit it):

PRIVATE_KEY=0x...          # your wallet private key
# later: API credentials derived from the key

Read the official docs: https://docs.polymarket.com (especially the Python SDK quickstart and trading sections). Older py-clob-client packages are archived — use the current unified polymarket-client.

Step 2: Understand the Markets and Data Sources

Polymarket runs recurring BTC “Up or Down” windows (5m, 15m, hourly, etc.). Each market has two outcomes (tokens): Up and Down. They resolve based on whether BTC closes higher or lower than the open/price-to-beat for that window.

You need three data streams:

BTC price data (OHLCV or high/low/close) — Binance, Coinbase, or similar (WebSocket preferred for low latency).
Market discovery — Gamma API (https://gamma-api.polymarket.com) to find currently active Up/Down markets and their token IDs.
Order book & trading — CLOB API (https://clob.polymarket.com) for midpoints, books, and placing/canceling orders.
Step 3: Implement the Core Aroon Signal

This is the heart of the system described in the post.

Aroon formulas (period 
𝑁
N, commonly 14 or 25 — tune later):

Aroon Up
=
100
×
𝑁
−
periods since highest high
𝑁
Aroon Up=100×
N
N−periods since highest high
	​

Aroon Down
=
100
×
𝑁
−
periods since lowest low
𝑁
Aroon Down=100×
N
N−periods since lowest low
	​

Aroon Oscillator
=
Aroon Up
−
Aroon Down
Aroon Oscillator=Aroon Up−Aroon Down

Logic:

Aroon Up > Aroon Down → Up bias
Aroon Down > Aroon Up → Down bias
|Oscillator| small (near zero) → neutral, skip

Simple pure-pandas version (or use pandas_ta.aroon):

python
import pandas as pd
import numpy as np


def compute_aroon(df: pd.DataFrame, period: int = 14):
    """
    df must have columns: high, low (and ideally close)
    Returns DataFrame with aroon_up, aroon_down, aroon_osc
    """
    high = df['high']
    low = df['low']


    # periods since highest high / lowest low in the window
    periods_since_high = high.rolling(period + 1).apply(lambda x: period - np.argmax(x[::-1]), raw=True)
    periods_since_low  = low.rolling(period + 1).apply(lambda x: period - np.argmin(x[::-1]), raw=True)


    aroon_up   = 100 * (1 - periods_since_high / period)
    aroon_down = 100 * (1 - periods_since_low  / period)
    osc        = aroon_up - aroon_down


    return pd.DataFrame({
        'aroon_up': aroon_up,
        'aroon_down': aroon_down,
        'aroon_osc': osc
    }, index=df.index)


def get_signal(aroon_row, osc_threshold: float = 20.0):
    up = aroon_row['aroon_up']
    down = aroon_row['aroon_down']
    osc = aroon_row['aroon_osc']


    if abs(osc) < osc_threshold:
        return "NEUTRAL"
    if up > down:
        return "UP"
    else:
        return "DOWN"

Test this offline on historical BTC candles first.

Step 4: Design the Multi-Agent (Modular) Architecture

Treat “agents” as clean Python classes or functions that communicate via a shared state or message queue. Keep it simple at first.

Suggested roles (inspired by the post):

Spotter / Signal Agent: Runs Aroon on recent BTC data → emits UP / DOWN / NEUTRAL + confidence (oscillator magnitude).
Edge Agent: Looks at current Polymarket Up/Down prices vs. the signal. Decides if there is sufficient edge (e.g., market price of the favored side is still attractive).
Kelly / Sizer Agent: Position sizing (fractional Kelly or fixed fraction of bankroll, capped).
Risk Agent: Hard limits (max position, max daily loss, drawdown kill-switch, max exposure per market).
Execution / Taker-Closer Agent: Places, monitors, cancels orders; handles partial fills and market close.
Inventory / Balance Agent (optional): Tracks Up vs Down holdings if you ever hold both sides.

Start with a single process that calls these modules in a loop rather than true distributed agents.

Step 5: Discover Markets and Fetch Order Books

Use the public Gamma API to find active BTC Up/Down markets, then the CLOB for books and token IDs.

Example skeleton (adapt to the current polymarket-client methods):

python
from polymarket import PublicClient  # or AsyncPublicClient


# Pseudocode — check latest docs for exact method names
with PublicClient() as client:
    markets = client.list_markets(...)  # filter for active crypto / BTC up-down
    # or search by slug patterns like "btc-updown-15m-..."

For each relevant market you need the Yes/No (Up/Down) token IDs and the current best bid/ask or midpoint.

Step 6: Execution, Risk, and the Main Loop
Fetch latest BTC OHLCV (or tick data aggregated into bars matching your Aroon period).
Compute Aroon → get signal.
If signal is clear and Risk Agent approves:
Choose the corresponding token (Up or Down).
Check Edge Agent (is the price still attractive?).
Size via Sizer.
Place a limit or market order via the authenticated SecureClient.
Monitor fills, cancel stale orders, redeem after resolution.
Log everything (signal, prices, size, fill, PnL).

Always implement a dry-run / paper mode that simulates fills against the live book without sending real orders.

Step 7: Backtesting and Paper Trading
Collect historical BTC candles + historical Polymarket prices if available (or simulate reasonable market prices).
Run the signal + simple entry rules and measure win rate, average edge after fees, max drawdown.
Then run a live paper loop for days/weeks while watching real markets.
Step 8: Monitoring, Logging, and Iteration
Dashboard or simple console + CSV/ database of every signal and trade.
Track realized PnL, fees paid, fill rates, and how often the oscillator threshold is crossed.
Tune 
𝑁
N, oscillator threshold, size rules, and time-of-window filters (many systems avoid the last few seconds or the first noisy seconds).
Step 9: Going Live (Very Carefully)
Tiny size only.
Hard kill-switches.
Separate “hot” wallet with limited funds.
Monitor latency and rate limits.
Understand fees and how they affect short-horizon edges.

Recommended next action: Tell me which step you want to dive into first and I will give concrete, runnable code for it. Good starting points:

“Give me a complete Aroon + signal class with example usage on Binance data”
“Show how to discover current BTC 15-minute Up/Down markets with the official SDK”
“Sketch the main paper-trading loop”

Which part shall we build right now?


---

**USER:**
Can you prepare this for me so I can upload to my GitHub?

**GROK:**

Here’s a clean, ready-to-upload GitHub project skeleton for an educational Aroon-based Polymarket BTC Up/Down trend system.

It is deliberately paper-trading first, modular (“multi-agent” style), and includes strong risk warnings. Live trading is opt-in and incomplete by design so you stay in control.

Project structure
polymarket-aroon-trend-bot/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── config.yaml
├── src/
│   ├── __init__.py
│   ├── signals/
│   │   └── aroon.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── signal_agent.py
│   │   ├── risk_agent.py
│   │   ├── sizer.py
│   │   └── execution_agent.py
│   ├── data/
│   │   ├── btc_feed.py
│   │   └── polymarket_client.py
│   ├── paper_trader.py
│   └── main.py
├── examples/
│   └── run_aroon_signal.py
└── tests/
    └── test_aroon.py

Copy the files below into that structure, then:

bash
git init
git add .
git commit -m "Initial educational Aroon Polymarket trend bot (paper mode)"
# create repo on GitHub and push
1. README.md
markdown
# Polymarket Aroon Trend Bot (Educational)


Educational multi-module trading system inspired by public Aroon-based BTC "Up or Down" strategies on Polymarket.


**This is NOT financial advice.**
Past performance claims online are not guarantees. Prediction markets involve substantial risk of loss. Fees, slippage, latency, and competition can eliminate any edge.


**Default mode = paper trading only.**
Live trading requires you to explicitly enable it and is at your own risk.


## Features
- Aroon Up / Down + Oscillator signal generation
- Modular “agents”: Signal, Risk, Sizer, Execution
- BTC price feed (via ccxt / Binance)
- Polymarket market discovery & order book scaffolding (official `polymarket-client`)
- Paper trading loop with logging
- Configurable thresholds and risk limits


## Quick Start (Paper Mode)


```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt


cp .env.example .env              # edit if needed (not required for pure paper)
python -m src.main
Configuration

Edit config.yaml for:

Aroon period
Oscillator threshold
Position sizing
Risk limits
Paper vs live flag
Important Notes
Always start with paper trading for weeks.
Never put your private key in code or commit it.
Polymarket has geo-restrictions and terms of service.
Market discovery for recurring BTC Up/Down windows changes over time — you will need to adapt the discovery logic.
This code is a starting point, not a production system.
Disclaimer

Use at your own risk. The authors and contributors accept no liability for any losses.



---


### 2. `requirements.txt`

pandas>=2.0 numpy>=1.24 pandas-ta>=0.3.14b ccxt>=4.0 python-dotenv>=1.0 pyyaml>=6.0 polymarket-client>=0.13.0 requests>=2.31



---


### 3. `.gitignore`

venv/ pycache/ *.pyc .env *.log .DS_Store .idea/ .vscode/ data/ logs/ *.csv



---


### 4. `.env.example`
Required only for live trading

POLYMARKET_PRIVATE_KEY=0x_your_private_key_here POLYMARKET_WALLET_ADDRESS=0x_your_wallet_or_funder_address

Optional
POLYMARKET_BUILDER_CODE=...


---


### 5. `config.yaml`


```yaml
mode: paper          # "paper" or "live" (live is dangerous)


aroon:
  period: 14
  osc_threshold: 25.0   # ignore signals when |oscillator| < this


sizing:
  bankroll_usd: 1000.0
  risk_fraction: 0.02   # 2% of bankroll per trade
  max_position_usd: 50.0


risk:
  max_daily_loss_usd: 100.0
  max_open_positions: 3
  kill_switch_drawdown_pct: 15.0


btc_feed:
  exchange: binance
  symbol: BTC/USDT
  timeframe: 1m        # or 5m — match your Aroon period style
  limit: 100


loop:
  sleep_seconds: 30
6. Core source files

src/signals/aroon.py

python
"""Aroon indicator + simple directional signal."""


from __future__ import annotations
import pandas as pd
import numpy as np


def compute_aroon(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Expects columns: high, low
    Returns DataFrame with aroon_up, aroon_down, aroon_osc
    """
    if not {"high", "low"}.issubset(df.columns):
        raise ValueError("DataFrame must contain 'high' and 'low' columns")


    high = df["high"]
    low = df["low"]


    def periods_since_extreme(series: pd.Series, find_max: bool) -> pd.Series:
        def _func(x):
            if find_max:
                idx = np.argmax(x[::-1])
            else:
                idx = np.argmin(x[::-1])
            return period - idx
        return series.rolling(period + 1).apply(_func, raw=True)


    periods_high = periods_since_extreme(high, find_max=True)
    periods_low = periods_since_extreme(low, find_max=False)


    aroon_up = 100 * (1 - periods_high / period)
    aroon_down = 100 * (1 - periods_low / period)
    osc = aroon_up - aroon_down


    return pd.DataFrame(
        {
            "aroon_up": aroon_up,
            "aroon_down": aroon_down,
            "aroon_osc": osc,
        },
        index=df.index,
    )


def get_signal(aroon_row: pd.Series, osc_threshold: float = 25.0) -> str:
    """Return 'UP', 'DOWN', or 'NEUTRAL'."""
    if pd.isna(aroon_row["aroon_osc"]):
        return "NEUTRAL"
    if abs(aroon_row["aroon_osc"]) < osc_threshold:
        return "NEUTRAL"
    if aroon_row["aroon_up"] > aroon_row["aroon_down"]:
        return "UP"
    return "DOWN"

src/agents/signal_agent.py

python
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from src.signals.aroon import compute_aroon, get_signal


[@dataclass](/dataclass)
class SignalResult:
    signal: str          # UP / DOWN / NEUTRAL
    aroon_up: float
    aroon_down: float
    oscillator: float
    confidence: float    # 0-1 based on |osc|


class SignalAgent:
    def __init__(self, period: int = 14, osc_threshold: float = 25.0):
        self.period = period
        self.osc_threshold = osc_threshold


    def generate(self, ohlcv: pd.DataFrame) -> SignalResult:
        aroon = compute_aroon(ohlcv, self.period)
        last = aroon.iloc[-1]
        signal = get_signal(last, self.osc_threshold)
        conf = min(abs(last["aroon_osc"]) / 100.0, 1.0)
        return SignalResult(
            signal=signal,
            aroon_up=float(last["aroon_up"]),
            aroon_down=float(last["aroon_down"]),
            oscillator=float(last["aroon_osc"]),
            confidence=conf,
        )

src/agents/risk_agent.py

python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


[@dataclass](/dataclass)
class RiskState:
    daily_pnl: float = 0.0
    open_positions: int = 0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    killed: bool = False


class RiskAgent:
    def __init__(
        self,
        max_daily_loss: float,
        max_open: int,
        kill_drawdown_pct: float,
        starting_equity: float,
    ):
        self.max_daily_loss = max_daily_loss
        self.max_open = max_open
        self.kill_drawdown_pct = kill_drawdown_pct
        self.state = RiskState(
            peak_equity=starting_equity,
            current_equity=starting_equity,
        )


    def update_equity(self, equity: float):
        self.state.current_equity = equity
        self.state.peak_equity = max(self.state.peak_equity, equity)
        dd = (self.state.peak_equity - equity) / self.state.peak_equity * 100
        if dd >= self.kill_drawdown_pct:
            self.state.killed = True


    def can_trade(self) -> bool:
        if self.state.killed:
            return False
        if self.state.daily_pnl <= -self.max_daily_loss:
            return False
        if self.state.open_positions >= self.max_open:
            return False
        return True


    def register_open(self):
        self.state.open_positions += 1


    def register_close(self, pnl: float):
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.daily_pnl += pnl

src/agents/sizer.py

python
from __future__ import annotations


class Sizer:
    def __init__(self, bankroll: float, risk_fraction: float, max_position: float):
        self.bankroll = bankroll
        self.risk_fraction = risk_fraction
        self.max_position = max_position


    def size_usd(self, confidence: float = 1.0) -> float:
        raw = self.bankroll * self.risk_fraction * confidence
        return min(raw, self.max_position)

src/agents/execution_agent.py (paper-first)

python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import logging


logger = logging.getLogger(__name__)


[@dataclass](/dataclass)
class PaperOrder:
    side: str
    token: str
    size_usd: float
    signal: str
    timestamp: datetime
    status: str = "FILLED_PAPER"


class ExecutionAgent:
    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.orders: list[PaperOrder] = []


    def place(self, signal: str, size_usd: float, token_id: str = "PAPER") -> PaperOrder:
        if self.mode != "paper":
            raise NotImplementedError(
                "Live execution is intentionally left as an exercise. "
                "Implement carefully with AsyncSecureClient.place_limit_order / place_market_order "
                "and thorough testing."
            )


        order = PaperOrder(
            side="BUY",
            token=token_id,
            size_usd=size_usd,
            signal=signal,
            timestamp=datetime.now(timezone.utc),
        )
        self.orders.append(order)
        logger.info(f"[PAPER] {signal} order size=${size_usd:.2f}")
        return order

src/data/btc_feed.py

python
from __future__ import annotations
import ccxt
import pandas as pd


def fetch_ohlcv(
    exchange_id: str = "binance",
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    limit: int = 100,
) -> pd.DataFrame:
    exchange = getattr(ccxt, exchange_id)()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df

src/data/polymarket_client.py (scaffold only)

python
"""
Scaffold for official polymarket-client.
Adapt market discovery to current BTC Up/Down slug patterns.
See https://docs.polymarket.com
"""


from __future__ import annotations
import os
from typing import Optional


# from polymarket import AsyncPublicClient, AsyncSecureClient


async def get_public_client():
    # async with AsyncPublicClient() as client:
    #     ...
    raise NotImplementedError("Implement with current polymarket-client docs")


async def get_secure_client():
    # private_key = os.environ["POLYMARKET_PRIVATE_KEY"]
    # client = await AsyncSecureClient.create(private_key=private_key)
    raise NotImplementedError("Live client – enable only after paper success")

src/paper_trader.py

python
from __future__ import annotations
import logging
from src.agents.signal_agent import SignalAgent
from src.agents.risk_agent import RiskAgent
from src.agents.sizer import Sizer
from src.agents.execution_agent import ExecutionAgent
from src.data.btc_feed import fetch_ohlcv


logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, config: dict):
        self.config = config
        self.signal_agent = SignalAgent(
            period=config["aroon"]["period"],
            osc_threshold=config["aroon"]["osc_threshold"],
        )
        self.risk = RiskAgent(
            max_daily_loss=config["risk"]["max_daily_loss_usd"],
            max_open=config["risk"]["max_open_positions"],
            kill_drawdown_pct=config["risk"]["kill_switch_drawdown_pct"],
            starting_equity=config["sizing"]["bankroll_usd"],
        )
        self.sizer = Sizer(
            bankroll=config["sizing"]["bankroll_usd"],
            risk_fraction=config["sizing"]["risk_fraction"],
            max_position=config["sizing"]["max_position_usd"],
        )
        self.execution = ExecutionAgent(mode=config["mode"])


    def step(self):
        if not self.risk.can_trade():
            logger.warning("Risk limits hit – skipping")
            return


        ohlcv = fetch_ohlcv(
            exchange_id=self.config["btc_feed"]["exchange"],
            symbol=self.config["btc_feed"]["symbol"],
            timeframe=self.config["btc_feed"]["timeframe"],
            limit=self.config["btc_feed"]["limit"],
        )


        result = self.signal_agent.generate(ohlcv)
        logger.info(
            f"Signal={result.signal} | Osc={result.oscillator:.1f} | Conf={result.confidence:.2f}"
        )


        if result.signal == "NEUTRAL":
            return


        size = self.sizer.size_usd(result.confidence)
        order = self.execution.place(result.signal, size)
        self.risk.register_open()
        # In a real system you would later register_close with actual PnL

src/main.py

python
from __future__ import annotations
import time
import logging
import yaml
from pathlib import Path
from src.paper_trader import PaperTrader


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    with open(Path(__file__).parent.parent / "config.yaml") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    if config["mode"] != "paper":
        logger.error("Live mode is disabled in this educational skeleton.")
        return


    trader = PaperTrader(config)
    logger.info("Starting paper trading loop (Ctrl+C to stop)")


    try:
        while True:
            trader.step()
            time.sleep(config["loop"]["sleep_seconds"])
    except KeyboardInterrupt:
        logger.info("Stopped by user")


if __name__ == "__main__":
    main()

src/__init__.py and src/agents/__init__.py can be empty.

examples/run_aroon_signal.py

python
from src.data.btc_feed import fetch_ohlcv
from src.agents.signal_agent import SignalAgent


df = fetch_ohlcv(limit=50)
agent = SignalAgent(period=14, osc_threshold=20)
result = agent.generate(df)
print(result)

tests/test_aroon.py

python
import pandas as pd
import numpy as np
from src.signals.aroon import compute_aroon, get_signal


def test_aroon_basic():
    n = 30
    df = pd.DataFrame({
        "high": np.linspace(100, 110, n),
        "low": np.linspace(99, 109, n),
    })
    aroon = compute_aroon(df, period=14)
    assert "aroon_up" in aroon.columns
    signal = get_signal(aroon.iloc[-1], osc_threshold=10)
    assert signal in {"UP", "DOWN", "NEUTRAL"}
How to upload
Create the folder structure and paste the files.
git init && git add . && git commit -m "Educational Aroon Polymarket trend bot – paper mode"
Create a new repository on GitHub (do not initialize with README).
git remote add origin https://github.com/YOUR_USERNAME/polymarket-aroon-trend-bot.git
git branch -M main && git push -u origin main

Add a clear MIT or educational license if you want.

Would you like me to expand any part (better market discovery, WebSocket feeds, full async live skeleton with proper warnings, Docker support, or a more complete backtester)? Just say which piece.


---

**USER:**
Can I add my Polymarket API key to the project

**GROK:**

Yes, but only safely — never hard-code it or commit it to GitHub.

Polymarket’s official Python SDK (polymarket-client) primarily authenticates with your wallet private key (not a classic exchange-style API key). The SDK derives the necessary credentials from that private key. Some setups also use a wallet/funder address or optional builder codes.

Correct way to add credentials

Use the existing .env file (already prepared in the project skeleton).

Edit .env (create it from .env.example if needed):

POLYMARKET_PRIVATE_KEY=0x_your_actual_private_key_here
POLYMARKET_WALLET_ADDRESS=0x_your_wallet_or_funder_address_here

The project’s .gitignore already excludes .env, so the real key will not be uploaded to GitHub when you push.

Load the values in code with python-dotenv (already in requirements.txt):

python
from dotenv import load_dotenv
import os


load_dotenv()


private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
wallet = os.getenv("POLYMARKET_WALLET_ADDRESS")

Pass them only when creating the secure client (for live mode):

python
from polymarket import AsyncSecureClient


client = await AsyncSecureClient.create(
    private_key=private_key,
    # wallet=wallet,   # include if required by current docs
)
Critical safety rules
Never put the real private key inside any .py file, config.yaml, or README.
Never commit .env (the .gitignore already protects you).
Keep mode: paper in config.yaml until you have thoroughly tested.
Use a dedicated wallet with limited funds for any live experiments.
Double-check the latest official docs (https://docs.polymarket.com) because authentication details can evolve.

Would you like me to update the project files so that:

Live mode cleanly loads from .env, and
The ExecutionAgent has a proper (still carefully gated) live path using AsyncSecureClient?

Just say the word and I’ll give you the exact updated code snippets.


---

**USER:**
How do I create a private key

**GROK:**

Here’s the safe way to create a private key for use with Polymarket (Polygon network).

A private key is a secret 64-character hexadecimal string (usually shown as 0x + 64 hex characters). Anyone who has it can control and steal all funds in the associated wallet. Treat it like the master password to your money.

Recommended methods (from safest to simplest)
1. Easiest for most people – MetaMask (Recommended starting point)
Install the official MetaMask browser extension from metamask.io (only use the official site).
Create a new wallet and write down the 12-word recovery phrase on paper (never store it digitally or take a screenshot).
Once the wallet is created:
Click the three dots → Account details → Export Private Key.
Enter your MetaMask password.
Copy the private key (it starts with 0x).
Switch the network to Polygon Mainnet inside MetaMask.
Put the private key only into your local .env file (never into code or GitHub).

This gives you both a private key and an address you can fund.

2. Generate one with Python (useful for bots)

You can generate a fresh key locally with the eth-account library:

bash
pip install eth-account

Then run this short script:

python
from eth_account import Account


# Generate a new random account
account = Account.create()


print("Address:     ", account.address)
print("Private key: ", account.key.hex())
Copy the private key (the long 0x... string) into your .env file.
Immediately delete or secure any file that printed the key.
Never run this on a shared computer or in an online notebook.
3. Hardware wallet (most secure for larger amounts)

Use a Ledger or Trezor. Exporting the private key from a hardware wallet is possible but not recommended for automated bots. For bots, most people use a separate “hot” software wallet with only a small amount of capital.

Important security rules
Never share the private key with anyone (including me).
Never paste it into chat, Discord, Telegram, email, or GitHub.
Store it only in your local .env file (which is already in .gitignore).
Use a dedicated wallet with limited funds for the bot — do not use your main savings wallet.
After creating the key, send a small test amount of USDC/pUSD on Polygon first and confirm everything works.
If the key is ever exposed, transfer all funds out immediately and abandon that wallet.
Next steps after you have the key
Put it in .env:
POLYMARKET_PRIVATE_KEY=0xYourPrivateKeyHere
POLYMARKET_WALLET_ADDRESS=0xYourAddressHere
Fund the address with a small amount of USDC on the Polygon network (you can bridge from Ethereum or buy on an exchange that supports Polygon withdrawals).
Keep the bot in mode: paper until you are fully comfortable.

Would you like me to also show you the exact code changes needed so the project cleanly loads the private key from .env and uses it with the official Polymarket SDK (still with live trading gated behind a clear warning)?


---

**USER:**
Give me the full script to get started

**GROK:**

Here’s a complete, ready-to-run starter package so you can get the paper-trading version working immediately.

1. Quick Setup (do this once)
bash
mkdir polymarket-aroon-bot
cd polymarket-aroon-bot


python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate


pip install pandas numpy pandas-ta ccxt python-dotenv pyyaml polymarket-client

Create these three files:

2. config.yaml
yaml
mode: paper                    # keep as "paper" until you are ready


aroon:
  period: 14
  osc_threshold: 25.0


sizing:
  bankroll_usd: 1000.0
  risk_fraction: 0.02
  max_position_usd: 50.0


risk:
  max_daily_loss_usd: 100.0
  max_open_positions: 3
  kill_switch_drawdown_pct: 15.0


btc_feed:
  exchange: binance
  symbol: BTC/USDT
  timeframe: 1m
  limit: 100


loop:
  sleep_seconds: 30
3. .env (optional for now – only needed later for live)
env
POLYMARKET_PRIVATE_KEY=0x_your_private_key_here
POLYMARKET_WALLET_ADDRESS=0x_your_wallet_address_here
4. Full starter script – main.py

Save this as main.py in the same folder:

python
#!/usr/bin/env python3
"""
Educational Aroon Trend Bot for Polymarket BTC Up/Down markets
Default = PAPER TRADING only
"""


from __future__ import annotations
import time
import logging
import yaml
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


import pandas as pd
import numpy as np
import ccxt
from dotenv import load_dotenv
import os


# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aroon-bot")


# -------------------------------------------------
# Load config
# -------------------------------------------------
def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


# -------------------------------------------------
# Aroon Indicator
# -------------------------------------------------
def compute_aroon(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]


    def periods_since(series: pd.Series, find_max: bool) -> pd.Series:
        def _func(window):
            if find_max:
                idx = np.argmax(window[::-1])
            else:
                idx = np.argmin(window[::-1])
            return period - idx
        return series.rolling(period + 1).apply(_func, raw=True)


    periods_high = periods_since(high, find_max=True)
    periods_low = periods_since(low, find_max=False)


    aroon_up = 100 * (1 - periods_high / period)
    aroon_down = 100 * (1 - periods_low / period)
    osc = aroon_up - aroon_down


    return pd.DataFrame({
        "aroon_up": aroon_up,
        "aroon_down": aroon_down,
        "aroon_osc": osc,
    }, index=df.index)


def get_signal(aroon_row: pd.Series, threshold: float = 25.0) -> str:
    if pd.isna(aroon_row["aroon_osc"]):
        return "NEUTRAL"
    if abs(aroon_row["aroon_osc"]) < threshold:
        return "NEUTRAL"
    return "UP" if aroon_row["aroon_up"] > aroon_row["aroon_down"] else "DOWN"


# -------------------------------------------------
# BTC Data Feed
# -------------------------------------------------
def fetch_btc_ohlcv(exchange_id: str, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


# -------------------------------------------------
# Simple Agents
# -------------------------------------------------
[@dataclass](/dataclass)
class SignalResult:
    signal: str
    oscillator: float
    confidence: float
    aroon_up: float
    aroon_down: float


class SignalAgent:
    def __init__(self, period: int, threshold: float):
        self.period = period
        self.threshold = threshold


    def generate(self, df: pd.DataFrame) -> SignalResult:
        aroon = compute_aroon(df, self.period)
        last = aroon.iloc[-1]
        signal = get_signal(last, self.threshold)
        conf = min(abs(float(last["aroon_osc"])) / 100.0, 1.0)
        return SignalResult(
            signal=signal,
            oscillator=float(last["aroon_osc"]),
            confidence=conf,
            aroon_up=float(last["aroon_up"]),
            aroon_down=float(last["aroon_down"]),
        )


class RiskAgent:
    def __init__(self, max_daily_loss: float, max_open: int, kill_dd: float, start_equity: float):
        self.max_daily_loss = max_daily_loss
        self.max_open = max_open
        self.kill_dd = kill_dd
        self.daily_pnl = 0.0
        self.open_positions = 0
        self.peak = start_equity
        self.equity = start_equity
        self.killed = False


    def can_trade(self) -> bool:
        if self.killed:
            return False
        if self.daily_pnl <= -self.max_daily_loss:
            return False
        if self.open_positions >= self.max_open:
            return False
        return True


    def register_open(self):
        self.open_positions += 1


    def update_equity(self, equity: float):
        self.equity = equity
        self.peak = max(self.peak, equity)
        dd = (self.peak - equity) / self.peak * 100
        if dd >= self.kill_dd:
            self.killed = True
            logger.warning("KILL SWITCH activated – drawdown limit hit")


class Sizer:
    def __init__(self, bankroll: float, fraction: float, max_pos: float):
        self.bankroll = bankroll
        self.fraction = fraction
        self.max_pos = max_pos


    def size(self, confidence: float = 1.0) -> float:
        return min(self.bankroll * self.fraction * confidence, self.max_pos)


class ExecutionAgent:
    def __init__(self, mode: str = "paper"):
        self.mode = mode
        self.orders = []


    def place(self, signal: str, size_usd: float) -> dict:
        order = {
            "time": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "size_usd": round(size_usd, 2),
            "status": "PAPER_FILLED",
        }
        self.orders.append(order)
        logger.info(f"PAPER ORDER → {signal} | size ${size_usd:.2f}")
        return order


# -------------------------------------------------
# Main loop
# -------------------------------------------------
def main():
    load_dotenv()
    config = load_config()


    if config["mode"] != "paper":
        logger.error("Live mode is disabled in this starter script for safety.")
        logger.error("Keep mode: paper until you fully understand the risks.")
        return


    logger.info("=" * 60)
    logger.info("Aroon Trend Bot – PAPER TRADING MODE")
    logger.info("=" * 60)


    signal_agent = SignalAgent(
        period=config["aroon"]["period"],
        threshold=config["aroon"]["osc_threshold"],
    )
    risk = RiskAgent(
        max_daily_loss=config["risk"]["max_daily_loss_usd"],
        max_open=config["risk"]["max_open_positions"],
        kill_dd=config["risk"]["kill_switch_drawdown_pct"],
        start_equity=config["sizing"]["bankroll_usd"],
    )
    sizer = Sizer(
        bankroll=config["sizing"]["bankroll_usd"],
        fraction=config["sizing"]["risk_fraction"],
        max_pos=config["sizing"]["max_position_usd"],
    )
    execution = ExecutionAgent(mode="paper")


    logger.info("Starting loop (Ctrl+C to stop)...")
    logger.info(f"Aroon period={config['aroon']['period']} | threshold={config['aroon']['osc_threshold']}")


    try:
        while True:
            if not risk.can_trade():
                logger.warning("Risk limits reached – skipping this cycle")
                time.sleep(config["loop"]["sleep_seconds"])
                continue


            # 1. Fetch BTC data
            df = fetch_btc_ohlcv(
                exchange_id=config["btc_feed"]["exchange"],
                symbol=config["btc_feed"]["symbol"],
                timeframe=config["btc_feed"]["timeframe"],
                limit=config["btc_feed"]["limit"],
            )


            # 2. Generate signal
            result = signal_agent.generate(df)


            logger.info(
                f"Signal: {result.signal:7} | "
                f"Osc: {result.oscillator:6.1f} | "
                f"Up: {result.aroon_up:5.1f} | "
                f"Down: {result.aroon_down:5.1f} | "
                f"Conf: {result.confidence:.2f}"
            )


            # 3. Act only on clear signals
            if result.signal != "NEUTRAL":
                size = sizer.size(result.confidence)
                execution.place(result.signal, size)
                risk.register_open()


            time.sleep(config["loop"]["sleep_seconds"])


    except KeyboardInterrupt:
        logger.info("Stopped by user")
        logger.info(f"Total paper orders placed: {len(execution.orders)}")


if __name__ == "__main__":
    main()
5. How to run it
bash
python main.py

You should see output like:

10:35:12 | INFO     | ============================================================
10:35:12 | INFO     | Aroon Trend Bot – PAPER TRADING MODE
10:35:12 | INFO     | ============================================================
10:35:12 | INFO     | Starting loop (Ctrl+C to stop)...
10:35:13 | INFO     | Signal: NEUTRAL | Osc:   8.3 | Up:  52.1 | Down:  43.8 | Conf: 0.08
10:35:43 | INFO     | Signal: UP      | Osc:  41.7 | Up:  78.6 | Down:  36.9 | Conf: 0.42
10:35:43 | INFO     | PAPER ORDER → UP | size $8.40
What this script does right now
Pulls live BTC 1-minute candles from Binance
Calculates Aroon Up / Down / Oscillator
Emits UP / DOWN / NEUTRAL signals
Places simulated (paper) orders when the signal is clear
Respects basic risk limits
Runs forever until you press Ctrl+C
Next steps when you are ready
Let it run in paper mode for several days and review the signals.
Add your private key to .env (the way we discussed earlier).
Ask me for the live-trading version (I will keep strong safety gates).

Would you like me to also give you:

A version that logs every signal to a CSV file, or
The next piece that discovers actual Polymarket BTC Up/Down markets?

Just tell me what you want next.