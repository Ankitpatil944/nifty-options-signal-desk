"""The single most important property of the system: no indicator or signal may use future bars.

For each strategy we compute indicators on the full history, then again on truncated histories,
and require the value at the cut point to be identical. Any leak of future data breaks this.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingbot.strategies import REGISTRY


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_prepare_is_causal(name: str, bars: pd.DataFrame) -> None:
    strategy = REGISTRY[name]()
    full = strategy.prepare(bars)
    rng = np.random.default_rng(0)
    for cut in rng.integers(50, len(bars), size=25):
        partial = strategy.prepare(bars.iloc[:cut])
        a, b = full.iloc[cut - 1], partial.iloc[-1]
        for col in full.columns:
            va, vb = a[col], b[col]
            if isinstance(va, float | np.floating) and (np.isnan(va) or np.isnan(vb)):
                assert np.isnan(va) and np.isnan(vb), f"{name}.{col} differs at {cut}"
            elif isinstance(va, float | np.floating):
                assert va == pytest.approx(vb, rel=1e-9), f"{name}.{col} differs at {cut}"
            else:
                assert va == vb, f"{name}.{col} differs at {cut}"


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_signals_identical_live_and_batch(name: str, bars: pd.DataFrame) -> None:
    """Signals found in a backtest pass must equal those found bar-by-bar, as the live runner does."""
    strategy = REGISTRY[name]()
    full = strategy.prepare(bars)
    batch = {i for i in range(len(full)) if strategy.check(full, i, "NIFTY")}
    for i in list(batch)[:10] + [len(bars) // 2, len(bars) // 3]:
        partial = strategy.prepare(bars.iloc[: i + 1])
        live = strategy.check(partial, i, "NIFTY")
        assert (live is not None) == (i in batch)


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_candidates_superset_of_signals(name: str, bars: pd.DataFrame) -> None:
    strategy = REGISTRY[name]()
    full = strategy.prepare(bars)
    mask = strategy.candidates(full).to_numpy()
    for i in range(len(full)):
        if strategy.check(full, i, "NIFTY") is not None:
            assert mask[i]
