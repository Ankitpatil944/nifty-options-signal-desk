"""Live candle feeds. Both feeds deliver the same events, so the runner can't tell them apart:

* KiteFeed   - real ticks from the Kite WebSocket, aggregated into candles.
* ReplayFeed - stored history played back at any speed, for demos and testing without a login.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from tradingbot.config import Settings
from tradingbot.data.store import CandleStore, resample

log = logging.getLogger(__name__)


@dataclass
class Candle:
    symbol: str
    start: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def as_row(self) -> dict[str, float]:
        return {"open": self.open, "high": self.high, "low": self.low, "close": self.close,
                "volume": self.volume}


CandleHandler = Callable[[Candle], Awaitable[None]]
TickHandler = Callable[[str, pd.Timestamp, float], Awaitable[None]]


def bucket_start(ts: pd.Timestamp, minutes: int, open_hhmm: tuple[int, int] = (9, 15)) -> pd.Timestamp:
    session_open = ts.normalize() + pd.Timedelta(hours=open_hhmm[0], minutes=open_hhmm[1])
    offset = (ts - session_open) // pd.Timedelta(minutes=minutes)
    return session_open + offset * pd.Timedelta(minutes=minutes)


class CandleBuilder:
    """Aggregates ticks into fixed-interval candles; returns the finished candle when a bucket rolls."""

    def __init__(self, symbol: str, minutes: int) -> None:
        self.symbol = symbol
        self.minutes = minutes
        self.current: Candle | None = None

    def on_tick(self, ts: pd.Timestamp, price: float) -> Candle | None:
        start = bucket_start(ts, self.minutes)
        finished = None
        if self.current is not None and start > self.current.start:
            finished, self.current = self.current, None
        if self.current is None:
            self.current = Candle(self.symbol, start, price, price, price, price)
        else:
            c = self.current
            c.high, c.low, c.close = max(c.high, price), min(c.low, price), price
        return finished

    def flush_if_due(self, now: pd.Timestamp, grace_s: float = 2.0) -> Candle | None:
        """Close the current candle once its interval has passed, even if no new tick arrived."""
        c = self.current
        if c is not None and now >= c.start + pd.Timedelta(minutes=self.minutes, seconds=grace_s):
            self.current = None
            return c
        return None


class ReplayFeed:
    """Plays stored candles back as if live. `speed` is seconds of wall time per candle."""

    def __init__(self, settings: Settings, symbols: list[str], replay_days: int = 1, speed: float = 1.0) -> None:
        self.settings = settings
        self.symbols = symbols
        self.replay_days = replay_days
        self.speed = speed
        store = CandleStore(settings.data_path, settings.timezone)
        self.frames = {s: resample(store.load(s, 1), settings.candle_interval) for s in symbols}
        days = sorted(set(self.frames[symbols[0]].index.normalize()))
        self.replay_from = days[-replay_days]

    def warmup(self, symbol: str) -> pd.DataFrame:
        df = self.frames[symbol]
        return df[df.index < self.replay_from]

    async def run(self, on_candle: CandleHandler, on_tick: TickHandler) -> None:
        bars = pd.concat(
            [df[df.index >= self.replay_from].assign(symbol=s) for s, df in self.frames.items()]
        ).sort_index(kind="stable")
        for ts, row in bars.iterrows():
            for price in (row["open"], row["high"], row["low"], row["close"]):
                await on_tick(row["symbol"], ts, float(price))
                await asyncio.sleep(self.speed / 8)
            await on_candle(Candle(row["symbol"], ts, row["open"], row["high"], row["low"], row["close"],
                                   row["volume"]))
            await asyncio.sleep(self.speed / 2)
        log.info("replay finished")


class KiteFeed:
    """Streams index ticks over KiteTicker (runs in its own thread) and builds candles."""

    def __init__(self, settings: Settings, symbols: list[str]) -> None:
        from tradingbot.data import kite

        self.settings = settings
        self.symbols = symbols
        self.tokens = {settings.instruments[s].kite_token: s for s in symbols}
        self.builders = {s: CandleBuilder(s, settings.candle_interval) for s in symbols}
        self._kite = kite
        self._history: dict[str, pd.DataFrame] = {}

    def warmup(self, symbol: str) -> pd.DataFrame:
        if symbol not in self._history:
            today = datetime.now().date()
            raw = self._kite.download_history(self.settings, symbol, today - timedelta(days=10), today, 1)
            df = resample(raw.tz_convert(self.settings.timezone) if raw.index.tz else
                          raw.tz_localize(self.settings.timezone), self.settings.candle_interval)
            now = pd.Timestamp.now(tz=self.settings.timezone)
            # Drop the still-forming candle; the live builder will produce it.
            self._history[symbol] = df[df.index < bucket_start(now, self.settings.candle_interval)]
        return self._history[symbol]

    async def run(self, on_candle: CandleHandler, on_tick: TickHandler) -> None:
        from kiteconnect import KiteTicker

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, pd.Timestamp, float]] = asyncio.Queue()
        tz = self.settings.timezone

        ticker = KiteTicker(self.settings.secrets.kite_api_key, self._kite.access_token(self.settings))

        def on_ticks(_ws: Any, ticks: list[dict[str, Any]]) -> None:
            now = pd.Timestamp.now(tz=tz)
            for t in ticks:
                symbol = self.tokens.get(t["instrument_token"])
                if symbol:
                    loop.call_soon_threadsafe(queue.put_nowait, (symbol, now, float(t["last_price"])))

        def on_connect(ws: Any, _resp: Any) -> None:
            ws.subscribe(list(self.tokens))
            ws.set_mode(ws.MODE_LTP, list(self.tokens))
            log.info("kite ticker connected")

        ticker.on_ticks = on_ticks
        ticker.on_connect = on_connect
        ticker.on_close = lambda _ws, code, reason: log.warning("ticker closed %s %s", code, reason)
        ticker.connect(threaded=True)  # KiteTicker reconnects on its own

        try:
            while True:
                try:
                    symbol, ts, price = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await on_tick(symbol, ts, price)
                    done = self.builders[symbol].on_tick(ts, price)
                    if done:
                        await on_candle(done)
                except TimeoutError:
                    pass
                now = pd.Timestamp.now(tz=tz)
                for builder in self.builders.values():
                    done = builder.flush_if_due(now)
                    if done:
                        await on_candle(done)
        finally:
            ticker.close()
