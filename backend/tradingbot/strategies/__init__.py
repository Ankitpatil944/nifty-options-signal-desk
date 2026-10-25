from __future__ import annotations

from tradingbot.strategies.base import Side, Signal, Strategy
from tradingbot.strategies.ema_trend import EmaTrend
from tradingbot.strategies.orb import OpeningRangeBreakout
from tradingbot.strategies.vwap_reversion import VwapReversion

REGISTRY: dict[str, type[Strategy]] = {
    cls.name: cls for cls in (OpeningRangeBreakout, EmaTrend, VwapReversion)
}


def build(name: str, **params: float) -> Strategy:
    try:
        return REGISTRY[name](**params)
    except KeyError:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(REGISTRY)}") from None


__all__ = ["REGISTRY", "Side", "Signal", "Strategy", "build"]
