from __future__ import annotations

import numpy as np
import pandas as pd

from tradingbot.indicators import bars_into_session
from tradingbot.strategies.base import Side, Signal, Strategy


class OpeningRangeBreakout(Strategy):
    name = "orb"
    label = "Opening range breakout"
    description = ("Marks the high and low of the first N minutes. The first close outside that range "
                   "signals a trade in the breakout direction, stopped at the opposite side.")
    default_params = {"range_minutes": 15, "rr": 2.0, "stop_buffer_pct": 0.0005, "max_range_pct": 0.008}
    param_grid = {"range_minutes": [15, 30], "rr": [1.5, 2.0, 2.5], "max_range_pct": [0.006, 0.01]}

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        day = out.index.normalize()
        diffs = out.index.to_series().diff().dropna()
        bar_minutes = max(1, int(diffs.min().total_seconds() // 60)) if len(diffs) else 5
        n = max(1, int(self.p("range_minutes") // bar_minutes))
        k = bars_into_session(out)
        in_range = k < n
        hi = out["high"].where(in_range).groupby(day).cummax()
        lo = out["low"].where(in_range).groupby(day).cummin()
        # Range is only known once it has finished forming.
        out["or_high"] = hi.groupby(day).ffill().where(~in_range)
        out["or_low"] = lo.groupby(day).ffill().where(~in_range)
        out["or_width_pct"] = (out["or_high"] - out["or_low"]) / out["close"]

        long_break = (out["close"] > out["or_high"]).astype(int)
        short_break = (out["close"] < out["or_low"]).astype(int)
        out["orb_long"] = (long_break == 1) & (long_break.groupby(day).cumsum() == 1)
        out["orb_short"] = (short_break == 1) & (short_break.groupby(day).cumsum() == 1)
        return out

    def candidates(self, df: pd.DataFrame) -> pd.Series:
        return df["orb_long"] | df["orb_short"]

    def check(self, df: pd.DataFrame, i: int, symbol: str) -> Signal | None:
        row = df.iloc[i]
        width = row["or_width_pct"]
        if np.isnan(width) or width > self.p("max_range_pct"):
            return None
        buf = row["close"] * self.p("stop_buffer_pct")
        rr = self.p("rr")
        # Tighter ranges tend to give cleaner breakouts.
        confidence = 0.4 + 0.4 * (1 - width / self.p("max_range_pct"))
        if row["orb_long"]:
            stop = row["or_low"] - buf
            target = row["close"] + rr * (row["close"] - stop)
            return self._signal(df, i, symbol, Side.LONG, stop, target,
                                f"Closed above opening range high {row['or_high']:.0f}", confidence)
        if row["orb_short"]:
            stop = row["or_high"] + buf
            target = row["close"] - rr * (stop - row["close"])
            return self._signal(df, i, symbol, Side.SHORT, stop, target,
                                f"Closed below opening range low {row['or_low']:.0f}", confidence)
        return None
