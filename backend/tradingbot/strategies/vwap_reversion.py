from __future__ import annotations

import numpy as np
import pandas as pd

from tradingbot.indicators import atr, rsi, session_vwap
from tradingbot.strategies.base import Side, Signal, Strategy


class VwapReversion(Strategy):
    name = "vwap_reversion"
    label = "VWAP reversion"
    description = ("Fades stretched moves: price more than N ATRs from session VWAP with an extreme RSI. "
                   "Targets a return to VWAP; skipped when the reward is smaller than the risk.")
    default_params = {"band_atr": 2.0, "atr_period": 14, "rsi_period": 14, "rsi_low": 25,
                      "rsi_high": 75, "atr_stop": 1.0}
    param_grid = {"band_atr": [1.5, 2.0, 2.5], "rsi_low": [20, 25, 30], "atr_stop": [0.75, 1.0, 1.5]}

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = atr(out, int(self.p("atr_period")))
        out["rsi"] = rsi(out["close"], int(self.p("rsi_period")))
        out["vwap"] = session_vwap(out)
        out["stretch"] = (out["close"] - out["vwap"]) / out["atr"]
        return out

    def candidates(self, df: pd.DataFrame) -> pd.Series:
        return df["stretch"].abs() > self.p("band_atr")

    def check(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        row = df.iloc[i]
        a, r, stretch = row["atr"], row["rsi"], row["stretch"]
        if np.isnan(a) or np.isnan(r) or a <= 0:
            return None
        band = self.p("band_atr")
        stop_dist = self.p("atr_stop") * a
        rsi_high = self.params.get("rsi_high", 100 - self.p("rsi_low"))
        confidence = 0.3 + min(0.45, 0.1 * (abs(stretch) - band))
        if stretch < -band and r < self.p("rsi_low"):
            target = row["vwap"]
            if target - row["close"] < stop_dist:
                return None
            return self._signal(df, i, symbol, Side.LONG, row["close"] - stop_dist, target,
                                f"{abs(stretch):.1f} ATR below VWAP, RSI {r:.0f}", confidence)
        if stretch > band and r > rsi_high:
            target = row["vwap"]
            if row["close"] - target < stop_dist:
                return None
            return self._signal(df, i, symbol, Side.SHORT, row["close"] + stop_dist, target,
                                f"{stretch:.1f} ATR above VWAP, RSI {r:.0f}", confidence)
        return None
