import numpy as np
import pandas as pd
import pytest

from backtest.runner import Backtester
from tests.conftest import ohlcv_frame, random_walk


def trend_cfg(make_config, **kw):
    return make_config(strategy="trend", trend_sma_period=20, sizing_mode="allocation",
                       use_stop_loss=False, timeframe="1d", **kw)


def strip(trades):
    return [(t["action"], t["ts"], round(t["price"], 10)) for t in trades]


@pytest.mark.parametrize("strategy", ["trend", "ma_rsi"])
def test_no_lookahead_future_data_does_not_change_past_trades(make_config, strategy):
    """Trades up to T must be identical whether or not data after T exists."""
    cfg = trend_cfg(make_config) if strategy == "trend" else make_config(timeframe="1d")
    df = ohlcv_frame(random_walk(400, seed=1))
    cutoff = df.index[300]

    with_future = Backtester(cfg).run(df, end=cutoff)
    without_future = Backtester(cfg).run(df[df.index < cutoff])
    assert strip(with_future["trade_log"]) == strip(without_future["trade_log"])
    assert with_future["total_return_pct"] == pytest.approx(without_future["total_return_pct"])


def test_trades_stay_inside_window(make_config):
    df = ohlcv_frame(random_walk(400, seed=2))
    start, end = df.index[150], df.index[300]
    r = Backtester(trend_cfg(make_config)).run(df, start=start, end=end)
    assert r["trade_log"], "expected some trades on a random walk"
    assert all(start <= t["ts"] < end for t in r["trade_log"])
    assert r["period_start"] == start and r["period_end"] < end


def test_buy_hold_matches_window_prices(make_config):
    df = ohlcv_frame(random_walk(300, seed=3))
    start = df.index[100]
    r = Backtester(trend_cfg(make_config)).run(df, start=start)
    expected = (df["close"].iloc[-1] / df["close"].iloc[99] - 1) * 100
    assert r["buy_hold_pct"] == pytest.approx(expected)


def test_trend_enters_on_breakout_candle(make_config):
    closes = np.r_[np.full(40, 100.0), np.full(10, 120.0)]
    df = ohlcv_frame(closes)
    r = Backtester(trend_cfg(make_config)).run(df)
    buys = [t for t in r["trade_log"] if t["action"] == "BUY"]
    assert buys and buys[0]["ts"] == df.index[40]
    assert r["open_position"] is not None


def test_window_before_warmup_raises(make_config):
    df = ohlcv_frame(random_walk(15, seed=4))
    with pytest.raises(ValueError):
        Backtester(trend_cfg(make_config)).run(df)
