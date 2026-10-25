"""Walk-forward validation.

The history is cut into rolling windows. In each window the parameter grid is optimised on the
training slice and the winner is run, untouched, on the following test slice. Stitching the test
slices together gives an out-of-sample track record - the honest number to quote.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from tradingbot.backtest import engine, metrics
from tradingbot.config import Settings
from tradingbot.strategies import REGISTRY

log = logging.getLogger(__name__)


@dataclass
class WalkForwardRequest:
    symbols: list[str]
    strategy: str
    train_days: int = 120
    test_days: int = 40
    objective: str = "sharpe"           # sharpe | net_pnl | profit_factor
    instrument: engine.InstrumentKind = "options"
    option_mode: str | None = None
    min_trades: int = 10


def grid(strategy: str) -> list[dict[str, float]]:
    space = REGISTRY[strategy].param_grid
    keys = list(space)
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*space.values())]


def _slice(frames: dict[str, pd.DataFrame], days: list[pd.Timestamp]) -> dict[str, pd.DataFrame]:
    lo, hi = days[0], days[-1] + pd.Timedelta(days=1)
    return {s: df[(df.index >= lo) & (df.index < hi)] for s, df in frames.items()}


def _score(m: dict[str, Any], objective: str, min_trades: int) -> float:
    if m.get("trades", 0) < min_trades:
        return float("-inf")
    value = m.get(objective)
    return float("-inf") if value is None else float(value)


def run(settings: Settings, frames: dict[str, pd.DataFrame], req: WalkForwardRequest) -> dict[str, Any]:
    days = sorted({ts.normalize() for df in frames.values() for ts in df.index})
    combos = grid(req.strategy)
    windows: list[dict[str, Any]] = []
    oos_trades: list[pd.DataFrame] = []

    start = 0
    while start + req.train_days + req.test_days <= len(days):
        train_days = days[start:start + req.train_days]
        test_days = days[start + req.train_days:start + req.train_days + req.test_days]
        train, test = _slice(frames, train_days), _slice(frames, test_days)

        best_params, best_score, best_metrics = combos[0], float("-inf"), {}
        for params in combos:
            res = engine.run(settings, REGISTRY[req.strategy](**params), train, engine.BacktestRequest(
                req.symbols, req.strategy, params, req.instrument, req.option_mode))
            score = _score(res.metrics, req.objective, req.min_trades)
            if score > best_score:
                best_params, best_score, best_metrics = params, score, res.metrics

        oos = engine.run(settings, REGISTRY[req.strategy](**best_params), test, engine.BacktestRequest(
            req.symbols, req.strategy, best_params, req.instrument, req.option_mode))
        if not oos.trades.empty:
            oos_trades.append(oos.trades)
        windows.append({
            "train": [train_days[0].date().isoformat(), train_days[-1].date().isoformat()],
            "test": [test_days[0].date().isoformat(), test_days[-1].date().isoformat()],
            "params": best_params,
            "train_score": None if best_score == float("-inf") else round(best_score, 3),
            "train_metrics": {k: best_metrics.get(k) for k in ("trades", "net_pnl", "sharpe", "win_rate")},
            "test_metrics": {k: oos.metrics.get(k) for k in ("trades", "net_pnl", "sharpe", "win_rate")},
        })
        log.info("window %s: params=%s oos_pnl=%s", windows[-1]["test"], best_params, oos.metrics.get("net_pnl"))
        start += req.test_days

    if not windows:
        raise ValueError(f"need at least {req.train_days + req.test_days} trading days, have {len(days)}")

    all_oos = pd.concat(oos_trades) if oos_trades else pd.DataFrame()
    test_span = pd.DatetimeIndex(days[req.train_days:start + req.train_days])
    equity = metrics.daily_equity(all_oos, test_span, settings.risk.capital)
    return {
        "request": req.__dict__,
        "windows": windows,
        "oos_metrics": metrics.summary(all_oos, equity, settings.risk.capital),
        "oos_equity": [{"date": d.date().isoformat(), "equity": round(float(v), 2)} for d, v in equity.items()],
        "grid_size": len(combos),
    }
