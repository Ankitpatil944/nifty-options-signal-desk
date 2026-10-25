"""Event-driven backtester.

Timeline for every bar, per symbol:
  1. fill a pending signal at this bar's open (signals are decided on the previous bar's close)
  2. check stop / target / square-off for the open position
  3. ask the strategy for a new signal (inside the entry window, when flat)

Nothing ever reads a bar before it has "happened", which is what keeps the results free of
look-ahead bias. Sizing, risk limits and costs use the same code as the live runner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time
from typing import Any

import numpy as np
import pandas as pd

from tradingbot.backtest import metrics
from tradingbot.backtest.fills import check_exit
from tradingbot.config import Settings
from tradingbot.positions import InstrumentKind, Position, open_position
from tradingbot.risk import RiskManager
from tradingbot.strategies import Strategy
from tradingbot.strategies.base import Signal

log = logging.getLogger(__name__)


@dataclass
class BacktestRequest:
    symbols: list[str]
    strategy: str
    params: dict[str, float] = field(default_factory=dict)
    instrument: InstrumentKind = "options"
    option_mode: str | None = None          # overrides settings.options.mode
    start: str | None = None
    end: str | None = None


@dataclass
class BacktestResult:
    request: BacktestRequest
    trades: pd.DataFrame
    equity: pd.Series                      # account equity after each trading day
    metrics: dict[str, Any]
    skipped: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        trades = self.trades.copy()
        for col in trades.select_dtypes(include=["datetimetz", "datetime"]).columns:
            trades[col] = trades[col].map(lambda t: t.isoformat())
        return {
            "request": self.request.__dict__,
            "metrics": self.metrics,
            "skipped": self.skipped,
            "equity": [{"date": d.date().isoformat(), "equity": round(float(v), 2)}
                       for d, v in self.equity.items()],
            "trades": trades.replace({np.nan: None}).to_dict(orient="records"),
        }


def _in_window(t: time, start: time, end: time) -> bool:
    return start <= t < end


def run(settings: Settings, strategy: Strategy, frames: dict[str, pd.DataFrame],
        request: BacktestRequest) -> BacktestResult:
    s = settings.session
    risk = RiskManager(settings.risk)
    prepared = {sym: strategy.prepare(df) for sym, df in frames.items()}
    candidate = {sym: strategy.candidates(df).to_numpy() for sym, df in prepared.items()}
    arrays = {sym: (df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy())
              for sym, df in prepared.items()}
    position_of = {sym: {} for sym in prepared}  # row position lookup by timestamp
    for sym, df in prepared.items():
        position_of[sym] = {ts: i for i, ts in enumerate(df.index)}

    timeline = sorted(set().union(*(df.index for df in prepared.values())))
    pending: dict[str, Signal | None] = dict.fromkeys(prepared)
    open_pos: dict[str, Position | None] = dict.fromkeys(prepared)
    trades: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    def close(sym: str, pos: Position, ts: pd.Timestamp, spot: float, reason: str) -> None:
        exit_prices = pos.leg_prices_at(spot, ts)
        exit_value = pos.value_at(spot, ts)
        gross = (exit_value - pos.entry_value) * pos.qty
        cost = pos.costs(settings, exit_prices)
        net = gross - cost.total
        planned_risk = pos.loss_per_lot_at_stop() * pos.lots
        risk.on_close(net)
        trades.append({
            "symbol": sym, "strategy": strategy.name, "side": str(pos.signal.side),
            "signal_ts": pos.signal.ts, "entry_ts": pos.entry_ts, "exit_ts": ts,
            "entry_spot": round(pos.entry_spot, 2), "exit_spot": round(spot, 2),
            "stop": pos.signal.stop, "target": pos.signal.target, "exit_reason": reason,
            "instrument": pos.instrument,
            "structure": pos.option.structure if pos.option else "future",
            "contract": pos.option.describe() if pos.option else f"{sym} FUT",
            "lots": pos.lots, "qty": pos.qty,
            "entry_value": round(pos.entry_value, 2), "exit_value": round(exit_value, 2),
            "gross_pnl": round(gross, 2), "costs": round(cost.total, 2), "net_pnl": round(net, 2),
            "r_multiple": round(net / planned_risk, 2) if planned_risk > 0 else None,
            "reason": pos.signal.reason, "confidence": pos.signal.confidence,
        })
        open_pos[sym] = None

    for ts in timeline:
        t = ts.time()
        for sym, df in prepared.items():
            i = position_of[sym].get(ts)
            if i is None:
                continue
            o, h, low = arrays[sym][0][i], arrays[sym][1][i], arrays[sym][2][i]

            sig = pending[sym]
            if sig is not None:
                pending[sym] = None
                if ts.normalize() != sig.ts.normalize():
                    skip("signal expired overnight")
                elif check_exit(sig.side, sig.stop, sig.target, o, o, o) is not None:
                    skip("gapped past stop or target")
                else:
                    pos = open_position(sig, ts, float(o), settings, request.instrument,
                                        option_mode=request.option_mode)
                    decision = risk.evaluate(ts.date(), pos.loss_per_lot_at_stop())
                    if decision.allowed:
                        pos.lots = decision.lots
                        risk.on_open()
                        open_pos[sym] = pos
                    else:
                        skip(decision.reason)

            pos = open_pos[sym]
            if pos is not None:
                if t >= s.square_off or ts.normalize() != pos.entry_ts.normalize():
                    close(sym, pos, ts, float(o), "TIME")
                else:
                    hit = check_exit(pos.signal.side, pos.signal.stop, pos.signal.target, o, h, low)
                    if hit:
                        close(sym, pos, ts, hit[1], hit[0])

            if (open_pos[sym] is None and candidate[sym][i] and _in_window(t, s.entry_start, s.entry_end)):
                signal = strategy.check(df, i, sym)
                if signal is not None:
                    pending[sym] = signal

    # Close anything left at the very end of the data.
    for sym, pos in open_pos.items():
        if pos is not None:
            df = prepared[sym]
            close(sym, pos, df.index[-1], float(df["close"].iat[-1]), "END")

    trade_df = pd.DataFrame(trades)
    days = pd.DatetimeIndex(sorted({ts.normalize() for ts in timeline}))
    equity = metrics.daily_equity(trade_df, days, settings.risk.capital)
    return BacktestResult(request, trade_df, equity, metrics.summary(trade_df, equity, settings.risk.capital),
                          skipped)
