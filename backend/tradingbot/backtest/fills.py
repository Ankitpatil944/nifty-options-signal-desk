"""Exit rules shared by the backtester and the live signal journal, so both score trades identically."""

from __future__ import annotations

from tradingbot.strategies.base import Side


def check_exit(side: Side, stop: float, target: float, open_: float, high: float,
               low: float) -> tuple[str, float] | None:
    """Return (reason, underlying exit price) if this bar ends the trade.

    Gaps through a level fill at the open. If one bar touches both stop and target we can't know
    which came first from OHLC alone, so we assume the stop (the pessimistic choice).
    """
    if side is Side.LONG:
        if open_ <= stop:
            return "STOP", open_
        if open_ >= target:
            return "TARGET", open_
        if low <= stop:
            return "STOP", stop
        if high >= target:
            return "TARGET", target
    else:
        if open_ >= stop:
            return "STOP", open_
        if open_ <= target:
            return "TARGET", open_
        if high >= stop:
            return "STOP", stop
        if low <= target:
            return "TARGET", target
    return None
