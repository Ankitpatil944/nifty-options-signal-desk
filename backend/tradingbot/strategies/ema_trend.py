from __future__ import annotations

import numpy as np
import pandas as pd

from tradingbot.indicators import atr, ema, session_vwap
from tradingbot.strategies.base import Side, Signal, Strategy


class EmaTrend(Strategy):
    name = "ema_trend"
    label = "EMA trend"
    description = ("Fast EMA crossing the slow EMA, confirmed by price on the same side of the session "
                   "VWAP. Stop is a multiple of ATR, target a fixed reward-to-risk.")
    default_params = {"fast": 9, "slow": 21, "atr_period": 14, "atr_stop": 1.5, "rr": 2.0}
    param_grid = {"fast": [5, 9], "slow": [21, 34], "atr_stop": [1.0, 1.5, 2.0], "rr": [1.5, 2.0]}

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(out["close"], int(self.p("fast")))
        out["ema_slow"] = ema(out["close"], int(self.p("slow")))
        out["atr"] = atr(out, int(self.p("atr_period")))
        out["vwap"] = session_vwap(out)
        above = out["ema_fast"] > out["ema_slow"]
        valid = out["ema_slow"].notna()
        prev_above = above.shift(1, fill_value=False)
        prev_valid = valid.shift(1, fill_value=False)
        out["cross_up"] = valid & prev_valid & above & ~prev_above
        out["cross_down"] = valid & prev_valid & ~above & prev_above
        return out

    def candidates(self, df: pd.DataFrame) -> pd.Series:
        return df["cross_up"] | df["cross_down"]

    def check(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        row = df.iloc[i]
        a = row["atr"]
        if np.isnan(a) or a <= 0:
            return None
        stop_dist = self.p("atr_stop") * a
        rr = self.p("rr")
        # Confidence grows with how far price already sits from VWAP in the trade direction.
        lean = abs(row["close"] - row["vwap"]) / a
        confidence = 0.35 + min(0.4, 0.15 * lean)
        if row["cross_up"] and row["close"] > row["vwap"]:
            return self._signal(df, i, symbol, Side.LONG, row["close"] - stop_dist,
                                row["close"] + rr * stop_dist, "EMA crossover up, above VWAP", confidence)
        if row["cross_down"] and row["close"] < row["vwap"]:
            return self._signal(df, i, symbol, Side.SHORT, row["close"] + stop_dist,
                                row["close"] - rr * stop_dist, "EMA crossover down, below VWAP", confidence)
        return None
