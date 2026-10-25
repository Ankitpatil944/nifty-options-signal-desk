"""Performance statistics computed from a trade list and a daily equity curve."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_equity(trades: pd.DataFrame, days: pd.DatetimeIndex, capital: float) -> pd.Series:
    if trades.empty:
        return pd.Series(capital, index=days, dtype=float)
    pnl = trades.groupby(trades["exit_ts"].map(lambda t: t.normalize()))["net_pnl"].sum()
    return capital + pnl.reindex(days, fill_value=0.0).cumsum()


def max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """(max drawdown in INR, as % of the running peak)."""
    peak = equity.cummax()
    dd = equity - peak
    pct = (dd / peak).min() * 100 if len(equity) else 0.0
    return float(dd.min() if len(dd) else 0.0), float(pct)


def summary(trades: pd.DataFrame, equity: pd.Series, capital: float) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "net_pnl": 0.0, "return_pct": 0.0, "note": "no trades"}

    pnl = trades["net_pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    daily = equity.diff().fillna(equity.iloc[0] - capital)
    daily_ret = daily / equity.shift().fillna(capital)
    std = daily_ret.std(ddof=1)
    downside = daily_ret[daily_ret < 0].std(ddof=1)
    dd_inr, dd_pct = max_drawdown(pd.concat([pd.Series([capital]), equity.reset_index(drop=True)]))
    years = max(len(equity) / TRADING_DAYS, 1 / TRADING_DAYS)
    final = float(equity.iloc[-1])
    hold = (trades["exit_ts"] - trades["entry_ts"]).dt.total_seconds() / 60

    def r(x: float, nd: int = 2) -> float | None:
        return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(x, nd)

    by_reason = trades["exit_reason"].value_counts().to_dict()
    by_side = trades.groupby("side")["net_pnl"].agg(["count", "sum"]).round(2).to_dict(orient="index")
    by_symbol = trades.groupby("symbol")["net_pnl"].agg(["count", "sum"]).round(2).to_dict(orient="index")

    return {
        "trades": n,
        "net_pnl": r(float(pnl.sum())),
        "gross_pnl": r(float(trades["gross_pnl"].sum())),
        "costs": r(float(trades["costs"].sum())),
        "return_pct": r((final / capital - 1) * 100),
        "cagr_pct": r(((final / capital) ** (1 / years) - 1) * 100) if final > 0 else None,
        "win_rate": r(len(wins) / n * 100, 1),
        "avg_win": r(float(wins.mean())) if len(wins) else 0.0,
        "avg_loss": r(float(losses.mean())) if len(losses) else 0.0,
        "profit_factor": r(float(wins.sum() / -losses.sum())) if losses.sum() < 0 else None,
        "expectancy": r(float(pnl.mean())),
        "avg_r": r(float(trades["r_multiple"].dropna().mean())) if trades["r_multiple"].notna().any() else None,
        "sharpe": r(float(daily_ret.mean() / std * math.sqrt(TRADING_DAYS))) if std > 0 else None,
        "sortino": r(float(daily_ret.mean() / downside * math.sqrt(TRADING_DAYS))) if downside > 0 else None,
        "max_drawdown": r(dd_inr),
        "max_drawdown_pct": r(dd_pct),
        "avg_hold_minutes": r(float(hold.mean()), 1),
        "best_trade": r(float(pnl.max())),
        "worst_trade": r(float(pnl.min())),
        "max_consecutive_losses": int(_max_streak(pnl.to_numpy() <= 0)),
        "cost_drag_pct": r(float(trades["costs"].sum() / max(abs(trades["gross_pnl"]).sum(), 1e-9) * 100), 1),
        "exit_reasons": by_reason,
        "by_side": by_side,
        "by_symbol": by_symbol,
        "days": len(equity),
    }


def _max_streak(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best
