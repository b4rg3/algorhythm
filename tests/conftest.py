"""Shared fixtures. Every test sets config values explicitly so a local .env can't change results."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from config import Config

BASE = dict(
    exchange="kraken",
    history_exchange="kucoin",
    symbol="DOGE/USDT",
    timeframe="15m",
    strategy="ma_rsi",
    short_window=9,
    long_window=21,
    rsi_period=14,
    rsi_overbought=70.0,
    rsi_oversold=30.0,
    rsi_oversold_buy=True,
    trend_period=0,
    trend_sma_period=200,
    trend_band=0.0,
    paper_balance_usdt=1000.0,
    risk_per_trade_pct=0.02,
    stop_loss_pct=0.03,
    sizing_mode="risk",
    allocation_pct=1.0,
    use_stop_loss=True,
    fee_pct=0.004,
    slippage_pct=0.0005,
    coingecko_id="dogecoin",
)


@pytest.fixture
def make_config():
    def _make(**overrides) -> Config:
        return replace(Config(), **{**BASE, **overrides})

    return _make


@pytest.fixture
def cfg(make_config) -> Config:
    return make_config()


def candle(close: float, open_: float | None = None, low: float | None = None, high: float | None = None) -> dict:
    """A single OHLC candle; open/low/high default to the close."""
    open_ = close if open_ is None else open_
    return {
        "open": open_,
        "high": max(open_, close) if high is None else high,
        "low": min(open_, close) if low is None else low,
        "close": close,
    }


def ohlcv_frame(closes, start="2025-01-01", freq="1D") -> pd.DataFrame:
    """OHLCV DataFrame from a sequence of closes (open = previous close, ±0.5% wicks)."""
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.005,
            "low": np.minimum(opens, closes) * 0.995,
            "close": closes,
            "volume": 1.0,
        },
        index=idx,
    )


def random_walk(n: int, seed: int = 0, start_price: float = 100.0, vol: float = 0.02) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return start_price * np.exp(np.cumsum(rng.normal(0, vol, n)))
