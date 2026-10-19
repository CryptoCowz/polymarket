"""Read-only Polymarket public data.

GET https://gamma-api.polymarket.com/events and
GET https://clob.polymarket.com/prices-history only.
This module has no order, wallet, or key methods.
"""

from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from aroonbot.data import USER_AGENT, _session

ET = ZoneInfo("America/New_York")
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def taker_fee(price: float, rate: float = 0.07) -> float:
    """Polymarket crypto taker fee approximation: rate * p * (1 - p) per share."""
    if not 0.0 <= price <= 1.0:
        raise ValueError("price must be in [0, 1]")
    if rate < 0:
        raise ValueError("fee rate must be non-negative")
    return float(rate * price * (1.0 - price))


def _loads(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def floor_window(now, minutes: int) -> pd.Timestamp:
    ts = pd.Timestamp(now)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    epoch = int(ts.timestamp())
    start = epoch - epoch % (minutes * 60)
    return pd.Timestamp(start, unit="s", tz="UTC")


def hourly_slugs(start: pd.Timestamp) -> list[str]:
    local = start.tz_convert(ET)
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    base = f"bitcoin-up-or-down-{local.strftime('%B').lower()}-{local.day}"
    return [f"{base}-{local.year}-{hour}{suffix}-et", f"{base}-{hour}{suffix}-et"]


def slug_candidates(start: pd.Timestamp, minutes: int) -> list[str]:
    if minutes in (5, 15):
        return [f"btc-updown-{minutes}m-{int(start.timestamp())}"]
    if minutes == 60:
        return hourly_slugs(start)
    raise ValueError("minutes must be 5, 15, or 60")


def last_at_or_before(history: list[dict], ts: int) -> float | None:
    points = [point for point in history if int(point["t"]) <= ts]
    if not points:
        return None
    points.sort(key=lambda point: int(point["t"]))
    return float(points[-1]["p"])


def prints_between(history: list[dict], start_ts: int, end_ts: int) -> list[dict]:
    """Prints strictly after start_ts and strictly before end_ts."""
    points = [point for point in history if start_ts < int(point["t"]) < end_ts]
    points.sort(key=lambda point: int(point["t"]))
    return points


class PublicPolymarket:
    def __init__(self, cache_dir: str | Path | None = "data/cache/pm", session: requests.Session | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.session = session or _session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def _get_json(self, url: str, params: dict):
        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def event_by_slug(self, slug: str) -> dict | None:
        payload = self._get_json(f"{GAMMA}/events", {"slug": slug})
        if isinstance(payload, list) and payload:
            return payload[0]
        return None

    def price_history(self, token_id: str, start_ts: int, end_ts: int) -> list[dict]:
        payload = self._get_json(
            f"{CLOB}/prices-history",
            {"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": 1},
        )
        history = payload.get("history", []) if isinstance(payload, dict) else payload
        return [{"t": int(point["t"]), "p": float(point["p"])} for point in history]

    def _cache_path(self, minutes: int, start_ts: int) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{minutes}m-{start_ts}.json"

    def window(self, start, minutes: int) -> dict:
        start = pd.Timestamp(start)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        start_ts = int(start.timestamp())
        end_ts = start_ts + minutes * 60
        path = self._cache_path(minutes, start_ts)
        if path is not None and path.exists():
            return json.loads(path.read_text())
        found = None
        slug_used = None
        for slug in slug_candidates(start, minutes):
            event = self.event_by_slug(slug)
            if not event or not event.get("markets"):
                continue
            market = event["markets"][0]
            end_date = pd.Timestamp(market.get("endDate"))
            if end_date.tzinfo is None:
                end_date = end_date.tz_localize("UTC")
            if minutes == 60 and end_date != start + pd.Timedelta(hours=1):
                continue
            found = (event, market)
            slug_used = slug
            break
        if found is None:
            result = {
                "ok": False,
                "slug": None,
                "minutes": minutes,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "resolved": False,
                "settled_up": None,
                "up_history": [],
                "down_history": [],
                "error": "market not found on the public gamma API",
            }
            return result
        event, market = found
        outcomes = _loads(market["outcomes"])
        prices = _loads(market["outcomePrices"])
        tokens = _loads(market["clobTokenIds"])
        up_i = outcomes.index("Up")
        down_i = outcomes.index("Down")
        up_history = self.price_history(str(tokens[up_i]), start_ts - 300, end_ts + 180)
        down_history = self.price_history(str(tokens[down_i]), start_ts - 300, end_ts + 180)
        closed = bool(market.get("closed"))
        settled = float(prices[up_i]) if closed else None
        resolved = closed and settled is not None and settled in (0.0, 1.0)
        result = {
            "ok": True,
            "slug": slug_used,
            "title": event.get("title"),
            "minutes": minutes,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "resolved": resolved,
            "settled_up": settled if resolved else None,
            "up_history": up_history,
            "down_history": down_history,
            "error": None,
        }
        if path is not None and resolved:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result))
        return result
