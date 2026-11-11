import ccxt
import numpy as np
import pandas as pd
import pytest

import data.coingecko as coingecko
import data.fetcher as fetcher_mod
from data.fetcher import DataFetcher
from tests.conftest import ohlcv_frame


class FakeExchange:
    """Serves candles from a fixed history, `page` at a time, like ccxt.fetch_ohlcv."""

    def __init__(self, first_ts_ms: int, n: int, tf_ms: int, page: int = 100, failures=()):
        self.rows = [[first_ts_ms + i * tf_ms, 1.0, 1.1, 0.9, 1.0 + i * 1e-4, 1.0] for i in range(n)]
        self.page = page
        self.failures = list(failures)
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        rows = [r for r in self.rows if since is None or r[0] >= since]
        return rows[: min(limit or self.page, self.page)]


def make_fetcher(config, exchange) -> DataFetcher:
    f = DataFetcher.__new__(DataFetcher)
    f.config, f.exchange_id, f.exchange = config, "fake", exchange
    return f


DAY_MS = 86_400_000
END = pd.Timestamp("2026-01-01", tz="UTC")


def test_fetch_history_paginates_full_window(make_config):
    cfg = make_config(timeframe="1d")
    first = int((END - pd.Timedelta(days=500)).timestamp() * 1000)
    ex = FakeExchange(first, 600, DAY_MS, page=50)
    df = make_fetcher(cfg, ex).fetch_history(days=400, end=END)

    assert len(df) == 400
    assert df.index[0] == END - pd.Timedelta(days=400)
    assert df.index[-1] == END - pd.Timedelta(days=1)  # last candle that closed by END
    assert df.index.is_monotonic_increasing and df.index.is_unique
    assert ex.calls >= 8


def test_fetch_history_rejects_truncated_history(make_config):
    """An exchange that only has recent data (like Kraken's 720-candle cap) must error."""
    cfg = make_config(timeframe="1d")
    first = int((END - pd.Timedelta(days=30)).timestamp() * 1000)
    ex = FakeExchange(first, 30, DAY_MS)
    with pytest.raises(RuntimeError, match="only returned"):
        make_fetcher(cfg, ex).fetch_history(days=400, end=END)


def test_fetch_history_retries_rate_limits(make_config, monkeypatch):
    monkeypatch.setattr(fetcher_mod.time, "sleep", lambda s: None)
    cfg = make_config(timeframe="1d")
    first = int((END - pd.Timedelta(days=100)).timestamp() * 1000)
    ex = FakeExchange(first, 100, DAY_MS, failures=[ccxt.RateLimitExceeded("slow down"),
                                                   ccxt.ExchangeError("Too many requests")])
    df = make_fetcher(cfg, ex).fetch_history(days=100, end=END)
    assert len(df) == 100


def test_fetch_history_does_not_retry_other_errors(make_config, monkeypatch):
    monkeypatch.setattr(fetcher_mod.time, "sleep", lambda s: None)
    cfg = make_config(timeframe="1d")
    ex = FakeExchange(0, 10, DAY_MS, failures=[ccxt.BadSymbol("no such market")])
    with pytest.raises(RuntimeError, match="no such market"):
        make_fetcher(cfg, ex).fetch_history(days=10, end=END)
    assert ex.calls == 1


def test_drop_incomplete_removes_forming_candle(make_config):
    cfg = make_config(timeframe="15m")
    now = pd.Timestamp.now(tz="UTC").floor("15min")
    idx = [now - pd.Timedelta(minutes=30), now - pd.Timedelta(minutes=15), now]
    df = pd.DataFrame({"close": [1, 2, 3]}, index=idx)
    assert list(make_fetcher(cfg, None)._drop_incomplete(df)["close"]) == [1, 2]


# ---------------------------------------------------------------- CoinGecko cross-check

def _cg_series(df: pd.DataFrame, tf: pd.Timedelta, offset_pct: float) -> pd.Series:
    """Hourly CoinGecko-like points, a few minutes off the hour, priced off the exchange."""
    closes = pd.Series(df["close"].values, index=df.index + tf)
    hourly = pd.date_range(df.index[0], df.index[-1] + tf, freq="1h", tz="UTC") + pd.Timedelta(minutes=3)
    price = closes.reindex(hourly, method="nearest") * (1 + offset_pct / 100)
    return price


@pytest.mark.parametrize("timeframe, freq", [("1d", "1D"), ("4h", "4h")])
def test_cross_check_matches_aligned_data(monkeypatch, timeframe, freq):
    df = ohlcv_frame(100 * np.exp(np.cumsum(np.full(60, 0.01))), freq=freq)
    tf = pd.Timedelta(freq)
    monkeypatch.setattr(coingecko, "fetch_prices", lambda *a, **k: _cg_series(df, tf, 0.1))
    check = coingecko.cross_check(df, "x", timeframe)
    assert check.ok
    assert check.median_abs_pct == pytest.approx(0.1, abs=0.01)
    assert check.points >= 10


def test_cross_check_flags_mismatch(monkeypatch):
    df = ohlcv_frame(np.full(60, 100.0))
    monkeypatch.setattr(coingecko, "fetch_prices", lambda *a, **k: _cg_series(df, pd.Timedelta("1D"), 5.0))
    assert not coingecko.cross_check(df, "x", "1d").ok
