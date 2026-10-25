"""Strategy interface shared by the backtester and the live runner.

A strategy does two things:
  prepare(df) - adds indicator columns. Must be causal (row t uses rows <= t only).
  check(df, i) - looks at row i of the prepared frame and returns a Signal or None.

Because live trading calls exactly the same two methods on the growing candle history,
the backtest is a faithful preview of what the live bot will suggest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

import pandas as pd


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


@dataclass
class Signal:
    ts: pd.Timestamp
    symbol: str
    side: Side
    entry: float          # reference price (signal bar close); fills happen on the next bar
    stop: float
    target: float
    strategy: str
    reason: str
    confidence: float = 0.5
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_points(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def reward_points(self) -> float:
        return abs(self.target - self.entry)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        d["side"] = str(self.side)
        return d


class Strategy(ABC):
    name: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str]
    default_params: ClassVar[dict[str, float]]
    param_grid: ClassVar[dict[str, list[float]]]

    def __init__(self, **params: float) -> None:
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}")
        self.params: dict[str, float] = {**self.default_params, **params}

    def p(self, key: str) -> float:
        return self.params[key]

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame: ...

    @abstractmethod
    def check(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None: ...

    def candidates(self, df: pd.DataFrame) -> pd.Series:
        """Rows where check() could possibly fire. Purely a speed-up for backtests; must be a
        superset of the rows check() accepts."""
        return pd.Series(True, index=df.index)

    def _signal(self, df: pd.DataFrame, i: int, symbol: str, side: Side, stop: float, target: float,
                reason: str, confidence: float = 0.5) -> Signal | None:
        entry = float(df["close"].iat[i])
        valid = stop < entry < target if side is Side.LONG else target < entry < stop
        if not valid:
            return None
        return Signal(ts=df.index[i], symbol=symbol, side=side, entry=entry, stop=round(stop, 2),
                      target=round(target, 2), strategy=self.name, reason=reason,
                      confidence=round(max(0.0, min(1.0, confidence)), 2))
