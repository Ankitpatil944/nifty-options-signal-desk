"""Causal indicators: every value at bar t depends only on bars <= t. Tests enforce this."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(gain.notna())


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP reset each session. Index candles carry no volume, so fall back to equal weights."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.normalize()
    weight = df["volume"].where(df["volume"] > 0, 1.0)
    pv = (typical * weight).groupby(day).cumsum()
    return pv / weight.groupby(day).cumsum()


def bars_into_session(df: pd.DataFrame) -> pd.Series:
    return df.groupby(df.index.normalize()).cumcount()
