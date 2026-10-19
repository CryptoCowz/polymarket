"""Public BTCUSDT 1-minute klines.

Monthly and daily files come from data.binance.vision. The forming day comes
from the public REST kline endpoint. Responses are cached under data/ (gitignored).
"""

from __future__ import annotations

import io
import os
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

USER_AGENT = "polymarket-btc-updown-lab/paper"
REST_BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.us",
    "https://api.binance.com",
]
VISION = "https://data.binance.vision/data/spot"
KLINE_COLUMNS = ["open", "high", "low", "close", "volume", "trades", "taker_buy"]


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def empty_frame() -> pd.DataFrame:
    frame = pd.DataFrame(columns=KLINE_COLUMNS)
    frame.index = pd.DatetimeIndex([], tz="UTC")
    return frame


def parse_kline_csv(raw: bytes) -> pd.DataFrame:
    """Parse a Binance kline CSV (no header). Timestamps may be ms or microseconds."""
    frame = pd.read_csv(io.BytesIO(raw), header=None, usecols=[0, 1, 2, 3, 4, 5, 8, 9])
    frame.columns = ["t", "open", "high", "low", "close", "volume", "trades", "taker_buy"]
    frame = frame[pd.to_numeric(frame.t, errors="coerce").notna()]
    if frame.empty:
        return empty_frame()
    timestamps = frame.t.to_numpy(dtype=np.int64)
    timestamps = np.where(timestamps > 10**14, timestamps // 1000, timestamps)
    out = pd.DataFrame(
        {
            "open": frame.open.to_numpy(dtype=float),
            "high": frame.high.to_numpy(dtype=float),
            "low": frame.low.to_numpy(dtype=float),
            "close": frame.close.to_numpy(dtype=float),
            "volume": frame.volume.to_numpy(dtype=float),
            "taker_buy": frame.taker_buy.to_numpy(dtype=float),
            "trades": frame.trades.to_numpy(dtype=int),
        }
    )
    out.index = pd.to_datetime(timestamps, unit="ms", utc=True)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def csv_from_zip(blob: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        name = archive.namelist()[0]
        return archive.read(name)


def _as_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def fetch_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    start_ms: int | None = None,
    end_ms: int | None = None,
    base: str | None = None,
    pause: float = 0.05,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Paginate the public REST kline endpoint. Read-only."""
    if start_ms is None or end_ms is None:
        raise ValueError("start_ms and end_ms are required")
    session = session or _session()
    env_base = os.environ.get("DATA_BASE_URL")
    bases = [base] if base else ([env_base] + REST_BASES if env_base else list(REST_BASES))
    rows: list = []
    cursor = int(start_ms)
    end_ms = int(end_ms)
    while cursor < end_ms:
        batch = None
        last_error: Exception | None = None
        for host in bases:
            try:
                response = session.get(
                    f"{host.rstrip('/')}/api/v3/klines",
                    params={
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": cursor,
                        "endTime": end_ms,
                        "limit": 1000,
                    },
                    timeout=20,
                )
                payload = response.json() if response.ok else None
                if response.ok and isinstance(payload, list):
                    batch = payload
                    bases = [host]
                    break
            except requests.RequestException as exc:
                last_error = exc
        if batch is None:
            raise RuntimeError(f"no kline source reachable ({last_error})")
        if not batch:
            break
        rows.extend(batch)
        nxt = int(batch[-1][0]) + 60_000
        if nxt <= cursor:
            break
        cursor = nxt
        if pause:
            time.sleep(pause)
    if not rows:
        return empty_frame()
    frame = pd.DataFrame(rows, columns="t o h l c v ct qv n tb tq i".split())
    frame = frame.drop_duplicates("t")
    out = pd.DataFrame(
        {
            "open": frame.o.astype(float),
            "high": frame.h.astype(float),
            "low": frame.l.astype(float),
            "close": frame.c.astype(float),
            "volume": frame.v.astype(float),
            "taker_buy": frame.tb.astype(float),
            "trades": frame.n.astype(int),
        }
    )
    out.index = pd.to_datetime(frame.t, unit="ms", utc=True)
    return out.sort_index()


def _atomic_pickle(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_pickle(tmp)
    tmp.replace(path)


class KlineStore:
    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        symbol: str = "BTCUSDT",
        session: requests.Session | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.symbol = symbol
        self.session = session or _session()

    def load(self, start, end, warmup: pd.Timedelta = pd.Timedelta(days=3)) -> pd.DataFrame:
        """Return 1-minute bars covering [start - warmup, end)."""
        start = _as_utc(start)
        end = _as_utc(end)
        if end <= start:
            raise ValueError("end must be after start")
        fetch_start = start - warmup
        today = pd.Timestamp.now(tz="UTC").floor("D")
        frames: list[pd.DataFrame] = []
        month_start = fetch_start.floor("D").replace(day=1)
        last_day = (end - pd.Timedelta(milliseconds=1)).floor("D")
        cursor = month_start
        while cursor <= last_day:
            next_month = (cursor + pd.Timedelta(days=32)).replace(day=1)
            if next_month.tzinfo is None:
                next_month = next_month.tz_localize("UTC")
            month_end_day = next_month - pd.Timedelta(days=1)
            if month_end_day < today:
                monthly = self._monthly(cursor.strftime("%Y-%m"))
                if monthly is not None:
                    frames.append(monthly)
                    cursor = next_month
                    continue
            day = max(cursor, fetch_start.floor("D"))
            stop = min(last_day, month_end_day)
            while day <= stop:
                frames.append(self._day(day, today, end))
                day += pd.Timedelta(days=1)
            cursor = next_month
        if not frames:
            raise RuntimeError("no BTC klines returned for that range")
        out = pd.concat(frames).sort_index()
        out = out[~out.index.duplicated(keep="last")]
        out = out[(out.index >= fetch_start) & (out.index < end)]
        if out.empty:
            raise RuntimeError("BTC klines were empty after slicing to the requested range")
        return out

    def _get(self, url: str) -> bytes | None:
        response = self.session.get(url, timeout=60)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    def _monthly(self, year_month: str) -> pd.DataFrame | None:
        path = self.cache_dir / f"{self.symbol}-1m-{year_month}.pkl"
        if path.exists():
            return pd.read_pickle(path)
        url = (
            f"{VISION}/monthly/klines/{self.symbol}/1m/{self.symbol}-1m-{year_month}.zip"
        )
        blob = self._get(url)
        if blob is None:
            return None
        frame = parse_kline_csv(csv_from_zip(blob))
        _atomic_pickle(frame, path)
        return frame

    def _day(self, day: pd.Timestamp, today: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        day = day.floor("D")
        day_end = min(day + pd.Timedelta(days=1), end)
        if day >= today:
            return fetch_klines(
                self.symbol,
                "1m",
                int(day.timestamp() * 1000),
                int(day_end.timestamp() * 1000) - 1,
                pause=0.02,
                session=self.session,
            )
        path = self.cache_dir / f"{self.symbol}-1m-{day.date()}.pkl"
        if path.exists():
            return pd.read_pickle(path)
        url = f"{VISION}/daily/klines/{self.symbol}/1m/{self.symbol}-1m-{day.date()}.zip"
        blob = self._get(url)
        if blob is None:
            frame = fetch_klines(
                self.symbol,
                "1m",
                int(day.timestamp() * 1000),
                int((day + pd.Timedelta(days=1)).timestamp() * 1000) - 1,
                pause=0.02,
                session=self.session,
            )
        else:
            frame = parse_kline_csv(csv_from_zip(blob))
        if not frame.empty:
            _atomic_pickle(frame, path)
        return frame


def load_klines(
    start,
    end,
    cache_dir: str | Path = "data/cache",
    symbol: str = "BTCUSDT",
    warmup: pd.Timedelta = pd.Timedelta(days=3),
):
    return KlineStore(cache_dir, symbol).load(start, end, warmup=warmup)
