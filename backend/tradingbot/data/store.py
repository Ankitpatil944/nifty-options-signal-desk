"""Parquet-backed candle store. One file per symbol and interval: data/candles/NIFTY_1m.parquet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradingbot.data import OHLCV


class CandleStore:
    def __init__(self, root: Path, tz: str = "Asia/Kolkata") -> None:
        self.root = root / "candles"
        self.root.mkdir(parents=True, exist_ok=True)
        self.tz = tz

    def path(self, symbol: str, interval: int) -> Path:
        return self.root / f"{symbol}_{interval}m.parquet"

    def exists(self, symbol: str, interval: int) -> bool:
        return self.path(symbol, interval).exists()

    def save(self, symbol: str, interval: int, df: pd.DataFrame) -> Path:
        df = validate_candles(df, self.tz)
        path = self.path(symbol, interval)
        df.to_parquet(path)
        return path

    def append(self, symbol: str, interval: int, df: pd.DataFrame) -> Path:
        if self.exists(symbol, interval):
            df = pd.concat([self.load(symbol, interval), df])
        return self.save(symbol, interval, df)

    def load(
        self,
        symbol: str,
        interval: int,
        start: str | pd.Timestamp | None = None,
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        path = self.path(symbol, interval)
        if not path.exists():
            raise FileNotFoundError(
                f"No {interval}m data for {symbol}. Run `tradingbot download` or `tradingbot synth` first."
            )
        df = pd.read_parquet(path)
        if start is not None:
            df = df[df.index >= _ts(start, self.tz)]
        if end is not None:
            df = df[df.index < _ts(end, self.tz) + pd.Timedelta(days=1)]
        return df

    def describe(self) -> list[dict[str, object]]:
        rows = []
        for path in sorted(self.root.glob("*.parquet")):
            symbol, interval = path.stem.rsplit("_", 1)
            df = pd.read_parquet(path, columns=["close"])
            rows.append(
                {
                    "symbol": symbol,
                    "interval": int(interval.rstrip("m")),
                    "rows": len(df),
                    "start": df.index.min().isoformat() if len(df) else None,
                    "end": df.index.max().isoformat() if len(df) else None,
                }
            )
        return rows


def _ts(value: str | pd.Timestamp, tz: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)


def validate_candles(df: pd.DataFrame, tz: str = "Asia/Kolkata") -> pd.DataFrame:
    """Normalise and sanity-check a candle frame: tz-aware sorted index, no duplicates, sane OHLC."""
    missing = set(OHLCV) - set(df.columns)
    if missing:
        raise ValueError(f"candles missing columns: {sorted(missing)}")
    df = df[OHLCV].copy()
    df.index = pd.DatetimeIndex(df.index)
    df.index = df.index.tz_localize(tz) if df.index.tz is None else df.index.tz_convert(tz)
    df.index.name = "ts"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1))
    if bad.any():
        # Repair rather than drop: vendors occasionally send a high/low that excludes open/close.
        df.loc[bad, "high"] = df.loc[bad, ["open", "high", "close"]].max(axis=1)
        df.loc[bad, "low"] = df.loc[bad, ["open", "low", "close"]].min(axis=1)
    df["volume"] = df["volume"].fillna(0)
    return df


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample 1-minute candles to N minutes, anchored to the 09:15 open, labelled by bar start."""
    if minutes == 1:
        return df
    out = df.resample(f"{minutes}min", origin="start_day", offset="15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open"])
