"""Live signal runner: candles in, sized option suggestions out (Telegram, journal, dashboard).

The runner never places orders. It calls the same strategy, sizing and exit code as the
backtester, so live results can be compared with backtest expectations like for like.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date, datetime
from typing import Any, Literal

import pandas as pd

from tradingbot.backtest.fills import check_exit
from tradingbot.config import Settings
from tradingbot.data.live import Candle, KiteFeed, ReplayFeed
from tradingbot.journal import Journal
from tradingbot.positions import Position, open_position
from tradingbot.risk import RiskManager
from tradingbot.strategies import REGISTRY, Strategy
from tradingbot.telegram import Telegram, format_close, format_signal

log = logging.getLogger(__name__)

Source = Literal["kite", "replay"]
HISTORY_BARS = 1500


class LiveRunner:
    def __init__(self, settings: Settings, journal: Journal) -> None:
        self.settings = settings
        self.journal = journal
        self.telegram = Telegram(settings.secrets.telegram_bot_token, settings.secrets.telegram_chat_id,
                                 settings.telegram.enabled)
        self.risk = RiskManager(settings.risk)
        self.strategies: list[Strategy] = [
            REGISTRY[name](**cfg.params) for name, cfg in settings.strategies.items() if cfg.enabled
        ]
        self.symbols = list(settings.instruments)
        self.subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.history: dict[str, pd.DataFrame] = {}
        self.last_price: dict[str, dict[str, Any]] = {}
        self.open: dict[int, Position] = {}
        self.source: Source | None = None
        self.started_at: datetime | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._quotes: Any = None
        self._close_stale()

    # ---- lifecycle -------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return any(not t.done() for t in self._tasks)

    async def start(self, source: Source, speed: float = 1.0, replay_days: int = 1) -> None:
        if self.running:
            raise RuntimeError("runner already running")
        self.risk = RiskManager(self.settings.risk)
        if source == "kite":
            feed: KiteFeed | ReplayFeed = KiteFeed(self.settings, self.symbols)
            from tradingbot.data.kite import KiteOptionQuotes
            self._quotes = KiteOptionQuotes(self.settings)
        else:
            feed = ReplayFeed(self.settings, self.symbols, replay_days=replay_days, speed=speed)
            self._quotes = None
        self.history = {s: feed.warmup(s).tail(HISTORY_BARS) for s in self.symbols}
        self.source, self.started_at = source, datetime.now()
        self._tasks = [asyncio.create_task(self._run_feed(feed), name="feed"),
                       asyncio.create_task(self.telegram.poll_commands(self._command), name="telegram")]
        await self.publish({"type": "status", "data": self.status()})
        await self.telegram.send(f"▶️ Signal bot started ({source}). Watching {', '.join(self.symbols)}.")

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks = []
        await self.publish({"type": "status", "data": self.status()})
        if self.source:
            await self.telegram.send("⏹ Signal bot stopped.")

    async def _run_feed(self, feed: KiteFeed | ReplayFeed) -> None:
        try:
            await feed.run(self._on_candle, self._on_tick)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("feed crashed")
            await self.publish({"type": "error", "data": {"message": str(exc)}})
            await self.telegram.send(f"⚠️ Feed stopped: {exc}")
        finally:
            await self.publish({"type": "status", "data": self.status(running=False)})

    # ---- events ----------------------------------------------------------------------------

    async def publish(self, event: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            if q.qsize() < 500:
                q.put_nowait(event)

    async def _on_tick(self, symbol: str, ts: pd.Timestamp, price: float) -> None:
        prev_close = self._prev_close(symbol, ts)
        self.last_price[symbol] = {
            "symbol": symbol, "ts": ts.isoformat(), "price": round(price, 2),
            "change_pct": round((price / prev_close - 1) * 100, 2) if prev_close else None,
        }
        await self.publish({"type": "tick", "data": self.last_price[symbol]})

    async def _on_candle(self, candle: Candle) -> None:
        sym = candle.symbol
        row = pd.DataFrame([candle.as_row()], index=pd.DatetimeIndex([candle.start], name="ts"))
        self.history[sym] = pd.concat([self.history[sym], row]).tail(HISTORY_BARS)
        await self.publish({"type": "candle", "data": {"symbol": sym, "ts": candle.start.isoformat(),
                                                        **{k: round(v, 2) for k, v in candle.as_row().items()}}})
        await self._track(candle)
        await self._scan(sym, candle)

    # ---- tracking open suggestions ----------------------------------------------------------

    async def _track(self, candle: Candle) -> None:
        s = self.settings.session
        for sid, pos in list(self.open.items()):
            if pos.signal.symbol != candle.symbol:
                continue
            hit = check_exit(pos.signal.side, pos.signal.stop, pos.signal.target,
                             candle.open, candle.high, candle.low)
            if hit is None and candle.start.time() >= s.square_off:
                hit = ("TIME", candle.close)
            if hit is None:
                continue
            reason, spot = hit
            ts = candle.start
            exit_value = pos.value_at(spot, ts)
            cost = pos.costs(self.settings, pos.leg_prices_at(spot, ts))
            pnl = round((exit_value - pos.entry_value) * pos.qty - cost.total, 2)
            self.journal.close(sid, reason, ts.isoformat(), round(spot, 2), round(exit_value, 2), pnl)
            self.risk.on_close(pnl)
            del self.open[sid]
            row = self.journal.get(sid) or {}
            await self.publish({"type": "signal_closed", "data": row})
            await self.telegram.send(format_close(row))

    # ---- new suggestions -------------------------------------------------------------------

    async def _scan(self, sym: str, candle: Candle) -> None:
        s = self.settings.session
        t = candle.start.time()
        if not (s.entry_start <= t < s.entry_end):
            return
        df = self.history[sym]
        for strategy in self.strategies:
            if any(p.signal.symbol == sym and p.signal.strategy == strategy.name for p in self.open.values()):
                continue
            prepared = strategy.prepare(df)
            signal = strategy.check(prepared, len(prepared) - 1, sym)
            if signal is None:
                continue
            ts = candle.start + pd.Timedelta(minutes=self.settings.candle_interval)
            pos = open_position(signal, ts, signal.entry, self.settings, "options",
                                quote=self._quote_fn(), expiries=self._expiries(sym))
            decision = self.risk.evaluate(ts.date(), pos.loss_per_lot_at_stop())
            if not decision.allowed:
                await self.publish({"type": "skipped", "data": {**signal.to_dict(), "why": decision.reason}})
                continue
            pos.lots = decision.lots
            self.risk.on_open()
            await self._emit(strategy, pos)

    async def _emit(self, strategy: Strategy, pos: Position) -> None:
        sig, opt = pos.signal, pos.option
        assert opt is not None
        row = {
            "created_at": pos.entry_ts.isoformat(), "source": self.source or "replay",
            "symbol": sig.symbol, "strategy": sig.strategy, "side": str(sig.side),
            "entry": round(sig.entry, 2), "stop": sig.stop, "target": sig.target, "reason": sig.reason,
            "confidence": sig.confidence, "contract": opt.describe(), "structure": opt.structure,
            "lots": pos.lots, "qty": pos.qty, "entry_value": round(opt.entry_value, 2),
            "value_at_stop": round(opt.est_value_at_stop, 2), "value_at_target": round(opt.est_value_at_target, 2),
            "option": opt.to_dict(),
        }
        sid = self.journal.add(row)
        self.open[sid] = pos
        saved = self.journal.get(sid) or row
        await self.publish({"type": "signal", "data": saved})
        await self.telegram.send(format_signal({
            **row, "strategy_label": strategy.label, "max_loss": opt.max_loss_per_unit,
            "risk_inr": pos.loss_per_lot_at_stop() * pos.lots, "priced_by": opt.legs[0].priced_by,
        }))

    # ---- helpers ---------------------------------------------------------------------------

    def _quote_fn(self) -> Any:
        if self._quotes is None:
            return None
        quotes = self._quotes

        def fetch(prefix: str, expiry: date, strike: float, right: str) -> float | None:
            symbol = quotes.tradingsymbol(prefix, expiry, strike, right)
            if not symbol:
                return None
            try:
                return quotes.ltp([symbol]).get(symbol)
            except Exception:  # quote failures fall back to the model price
                log.warning("quote failed for %s", symbol)
                return None
        return fetch

    def _expiries(self, sym: str) -> list[date] | None:
        if self._quotes is None:
            return None
        return self._quotes.expiries(self.settings.instruments[sym].option_prefix) or None

    def _prev_close(self, symbol: str, ts: pd.Timestamp) -> float | None:
        df = self.history.get(symbol)
        if df is None or df.empty:
            return None
        earlier = df[df.index < ts.normalize()]
        return float(earlier["close"].iat[-1]) if len(earlier) else None

    def _close_stale(self) -> None:
        """Suggestions left OPEN by a previous run can't be tracked any more."""
        for row in self.journal.open_signals():
            self.journal.close(row["id"], "UNTRACKED", row["created_at"], row["entry"], row["entry_value"], 0.0)

    def status(self, running: bool | None = None) -> dict[str, Any]:
        return {
            "running": self.running if running is None else running,
            "source": self.source,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "symbols": self.symbols,
            "strategies": [s.name for s in self.strategies],
            "prices": self.last_price,
            "risk": self.risk.snapshot(),
            "open_signals": len(self.open),
            "telegram": self.telegram.enabled,
            "option_mode": self.settings.options.mode,
        }

    async def _command(self, cmd: str) -> str:
        if cmd == "/pause":
            self.risk.paused = True
            await self.publish({"type": "status", "data": self.status()})
            return "⏸ Paused. No new suggestions until /resume."
        if cmd == "/resume":
            self.risk.paused = False
            await self.publish({"type": "status", "data": self.status()})
            return "▶️ Resumed."
        if cmd == "/pnl":
            r = self.risk.snapshot()
            return f"Today: {r['trades_today']} suggestion(s), est. realised P&L ₹{r['realised_today']:,.0f}"
        if cmd == "/open":
            if not self.open:
                return "No open suggestions."
            return "\n".join(f"#{sid} {p.signal.symbol} {p.signal.side} · {p.option.describe() if p.option else ''}"
                             for sid, p in self.open.items())
        if cmd == "/status":
            prices = ", ".join(f"{s} {v['price']:,.1f}" for s, v in self.last_price.items()) or "no ticks yet"
            state = "paused" if self.risk.paused else "running"
            return f"Bot {state} ({self.source}). {prices}. Open: {len(self.open)}."
        return "Commands: /status /open /pnl /pause /resume"
