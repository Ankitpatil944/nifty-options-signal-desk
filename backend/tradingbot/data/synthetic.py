"""Synthetic 1-minute index candles for development and demos without a data subscription.

Not a market model - just realistic enough to exercise the pipeline: overnight gaps, a U-shaped
intraday volatility profile, and a mix of trending and mean-reverting days. Never draw trading
conclusions from backtests on this data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BARS_PER_DAY = 375  # 09:15 to 15:29 inclusive


def generate(
    symbol: str,
    start: str,
    end: str,
    start_price: float,
    annual_vol: float,
    seed: int = 7,
    tz: str = "Asia/Kolkata",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed + sum(map(ord, symbol)))
    days = pd.bdate_range(start, end)
    minute_vol = annual_vol / np.sqrt(252 * BARS_PER_DAY)

    t = np.linspace(0, 1, BARS_PER_DAY)
    profile = 0.7 + 1.6 * (t - 0.5) ** 2 * 4  # higher vol at open and close
    profile /= np.sqrt((profile**2).mean())

    frames = []
    price = start_price
    for day in days:
        price *= np.exp(rng.normal(0, annual_vol / np.sqrt(252) * 0.35))  # overnight gap
        trend_day = rng.random() < 0.35
        drift = rng.choice([-1, 1]) * minute_vol * rng.uniform(0.08, 0.2) if trend_day else 0.0
        shocks = rng.standard_normal(BARS_PER_DAY) * minute_vol * profile
        rets = np.empty(BARS_PER_DAY)
        level = 0.0
        for i in range(BARS_PER_DAY):
            pull = 0.0 if trend_day else -0.02 * level  # range days revert toward the open
            rets[i] = drift + pull + shocks[i]
            level += rets[i]
        closes = price * np.exp(np.cumsum(rets))
        opens = np.concatenate([[price], closes[:-1]])
        wick = np.abs(rng.standard_normal((2, BARS_PER_DAY))) * minute_vol * profile * 0.6
        highs = np.maximum(opens, closes) * np.exp(wick[0])
        lows = np.minimum(opens, closes) * np.exp(-wick[1])
        idx = pd.date_range(day + pd.Timedelta(hours=9, minutes=15), periods=BARS_PER_DAY, freq="1min", tz=tz)
        frames.append(
            pd.DataFrame(
                {"open": opens, "high": highs, "low": lows, "close": closes, "volume": 0.0}, index=idx
            )
        )
        price = closes[-1]

    df = pd.concat(frames).round(2)
    df.index.name = "ts"
    return df
