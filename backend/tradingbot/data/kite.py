"""Zerodha Kite Connect integration: daily login, chunked historical download, instruments and quotes.

The kiteconnect package is an optional dependency (`pip install -e .[kite]`) and is imported lazily
so everything else runs without it.
"""

from __future__ import annotations

import json
import logging
import time as systime
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from tradingbot.config import Settings

log = logging.getLogger(__name__)

# Maximum days per historical_data request, per interval (Kite Connect limits).
CHUNK_DAYS = {1: 60, 3: 100, 5: 100, 10: 100, 15: 100, 30: 100, 60: 400}
KITE_INTERVAL = {1: "minute", 3: "3minute", 5: "5minute", 10: "10minute", 15: "15minute",
                 30: "30minute", 60: "60minute"}
REQUEST_GAP_S = 0.35  # stays under the ~3 requests/second historical API limit


class KiteNotConfigured(RuntimeError):
    pass


def _session_file(settings: Settings) -> Path:
    return settings.data_path / ".kite_session.json"


def _kite_class() -> Any:
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise KiteNotConfigured("kiteconnect is not installed. Run: pip install -e .[kite]") from exc
    return KiteConnect


def login_url(settings: Settings) -> str:
    if not settings.secrets.kite_api_key:
        raise KiteNotConfigured("Set KITE_API_KEY in backend/.env")
    return _kite_class()(api_key=settings.secrets.kite_api_key).login_url()


def complete_login(settings: Settings, request_token: str) -> None:
    """Exchange the request_token from the login redirect for today's access token and cache it."""
    if not (settings.secrets.kite_api_key and settings.secrets.kite_api_secret):
        raise KiteNotConfigured("Set KITE_API_KEY and KITE_API_SECRET in backend/.env")
    kite = _kite_class()(api_key=settings.secrets.kite_api_key)
    data = kite.generate_session(request_token, api_secret=settings.secrets.kite_api_secret)
    _session_file(settings).write_text(
        json.dumps({"access_token": data["access_token"], "date": date.today().isoformat()}),
        encoding="utf-8",
    )


def access_token(settings: Settings) -> str:
    path = _session_file(settings)
    if not path.exists():
        raise KiteNotConfigured("No Kite session. Run `tradingbot login` first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("date") != date.today().isoformat():
        raise KiteNotConfigured("Kite access token expired (they last one trading day). Run `tradingbot login`.")
    return str(data["access_token"])


def client(settings: Settings) -> Any:
    kite = _kite_class()(api_key=settings.secrets.kite_api_key)
    kite.set_access_token(access_token(settings))
    return kite


def date_chunks(start: date, end: date, interval: int) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive ranges no longer than the per-request limit."""
    step = CHUNK_DAYS[interval]
    chunks = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=step - 1), end)
        chunks.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return chunks


def download_history(settings: Settings, symbol: str, start: date, end: date, interval: int = 1) -> pd.DataFrame:
    kite = client(settings)
    token = settings.instruments[symbol].kite_token
    frames = []
    chunks = date_chunks(start, end, interval)
    for i, (a, b) in enumerate(chunks, 1):
        log.info("%s %s..%s (%d/%d)", symbol, a, b, i, len(chunks))
        rows = kite.historical_data(token, datetime.combine(a, datetime.min.time()),
                                    datetime.combine(b, datetime.max.time()), KITE_INTERVAL[interval])
        if rows:
            frames.append(pd.DataFrame(rows))
        systime.sleep(REQUEST_GAP_S)
    if not frames:
        raise RuntimeError(f"Kite returned no data for {symbol} between {start} and {end}")
    df = pd.concat(frames).set_index("date")
    return df[["open", "high", "low", "close", "volume"]]


class KiteOptionQuotes:
    """Resolves option contracts from the NFO instrument dump and fetches live premiums."""

    def __init__(self, settings: Settings) -> None:
        self.kite = client(settings)
        self._instruments = pd.DataFrame(self.kite.instruments("NFO"))
        self._instruments["expiry"] = pd.to_datetime(self._instruments["expiry"]).dt.date

    def expiries(self, prefix: str) -> list[date]:
        df = self._instruments
        rows = df[(df["name"] == prefix) & (df["segment"] == "NFO-OPT")]
        return sorted(rows["expiry"].unique())

    def tradingsymbol(self, prefix: str, expiry: date, strike: float, right: str) -> str | None:
        df = self._instruments
        rows = df[(df["name"] == prefix) & (df["expiry"] == expiry) & (df["strike"] == strike)
                  & (df["instrument_type"] == right)]
        return None if rows.empty else str(rows.iloc[0]["tradingsymbol"])

    def ltp(self, tradingsymbols: list[str]) -> dict[str, float]:
        keys = [f"NFO:{s}" for s in tradingsymbols]
        quotes = self.kite.ltp(keys)
        return {k.split(":", 1)[1]: float(v["last_price"]) for k, v in quotes.items()}
