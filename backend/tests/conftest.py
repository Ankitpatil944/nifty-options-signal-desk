from __future__ import annotations

import pandas as pd
import pytest

from tradingbot.config import load_settings
from tradingbot.data import synthetic
from tradingbot.data.store import resample


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def bars() -> pd.DataFrame:
    df = synthetic.generate("NIFTY", "2025-01-06", "2025-02-28", 24000.0, 0.14, seed=1)
    return resample(df, 5)


def make_bars(rows: list[tuple[float, float, float, float]], start: str = "2025-03-03 09:15") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="Asia/Kolkata", name="ts")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=0.0)
