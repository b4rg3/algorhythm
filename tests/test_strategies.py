import numpy as np
import pandas as pd
import pytest

from indicators.engine import IndicatorEngine
from risk.manager import RiskManager
from strategy.factory import make_strategy
from strategy.ma_rsi import MARSIStrategy
from strategy.trend import TrendStrategy
from tests.conftest import ohlcv_frame


# ---------------------------------------------------------------- risk manager

def test_risk_manager_sizing_and_stops(cfg):
    rm = RiskManager(cfg)
    assert rm.position_size(1000, 2.0) == pytest.approx(1000 * 0.02 / (2.0 * 0.03), rel=1e-6)
    assert rm.stop_loss_price(100, "BUY") == pytest.approx(97)
    assert rm.stop_loss_price(100, "SELL") == pytest.approx(103)


# ---------------------------------------------------------------- indicators

def test_crossover_marks_exactly_the_cross_candle(cfg):
    closes = np.r_[np.linspace(100, 60, 60), np.linspace(60, 120, 60)]
    df = IndicatorEngine(cfg).calculate(ohlcv_frame(closes))
    ups = df.index[df["crossover"] == 1]
    assert len(ups) == 1
    i = df.index.get_loc(ups[0])
    assert df["ema_short"].iloc[i] > df["ema_long"].iloc[i]
    assert df["ema_short"].iloc[i - 1] <= df["ema_long"].iloc[i - 1]


def test_trend_column_only_when_enabled(make_config):
    df = ohlcv_frame(np.linspace(100, 200, 300))
    assert "trend_ma" not in IndicatorEngine(make_config(trend_period=0)).calculate(df)
    out = IndicatorEngine(make_config(trend_period=100)).calculate(df)
    assert "trend_ma" in out and not out.isna().any().any()


# ---------------------------------------------------------------- MA/RSI rules

def rows(**last) -> pd.DataFrame:
    base = {"close": 1.0, "rsi": 50.0, "crossover": 0, "trend_ma": 0.5,
            "sma_short": 1, "sma_long": 1, "ema_short": 1, "ema_long": 1}
    return pd.DataFrame([base, {**base, **last}])


@pytest.mark.parametrize("last, overrides, expected", [
    ({"rsi": 25}, {}, "BUY"),                                   # oversold buy
    ({"rsi": 25}, {"rsi_oversold_buy": False}, "HOLD"),         # ...can be disabled
    ({"crossover": -1}, {}, "SELL"),                            # death cross
    ({"rsi": 75}, {}, "SELL"),                                  # overbought
    ({"crossover": 1, "rsi": 50}, {}, "BUY"),                   # golden cross
    ({"crossover": 1, "rsi": 75}, {}, "SELL"),                  # overbought beats cross
    ({"crossover": 1, "close": 0.4}, {"trend_period": 200}, "HOLD"),  # trend filter blocks
    ({"crossover": 1, "close": 0.6}, {"trend_period": 200}, "BUY"),   # ...allows in uptrend
    ({"rsi": 25, "close": 0.4}, {"trend_period": 200}, "HOLD"),       # blocks oversold buy too
    ({"crossover": -1, "close": 0.4}, {"trend_period": 200}, "SELL"), # exits still allowed
])
def test_ma_rsi_rules(make_config, last, overrides, expected):
    assert MARSIStrategy(make_config(**overrides)).signal(rows(**last)) == expected


def test_ma_rsi_needs_two_rows(cfg):
    assert MARSIStrategy(cfg).signal(rows().iloc[:1]) == "HOLD"


# ---------------------------------------------------------------- trend strategy

def test_trend_prepare_computes_sma_and_drops_warmup(make_config):
    df = ohlcv_frame(np.arange(1, 31, dtype=float))
    out = TrendStrategy(make_config(strategy="trend", trend_sma_period=10)).prepare(df)
    assert len(out) == 21
    assert out["sma"].iloc[0] == pytest.approx(np.mean(np.arange(1, 11)))


@pytest.mark.parametrize("close, band, expected", [
    (101, 0.0, "BUY"),
    (99, 0.0, "SELL"),
    (101, 0.02, "HOLD"),   # inside the band
    (99, 0.02, "HOLD"),
    (103, 0.02, "BUY"),
    (97, 0.02, "SELL"),
])
def test_trend_band(make_config, close, band, expected):
    s = TrendStrategy(make_config(strategy="trend", trend_band=band))
    assert s.signal(pd.DataFrame([{"close": close, "sma": 100.0}])) == expected


def test_factory(make_config):
    assert isinstance(make_strategy(make_config(strategy="trend")), TrendStrategy)
    assert isinstance(make_strategy(make_config(strategy="ma_rsi")), MARSIStrategy)
    with pytest.raises(ValueError):
        make_strategy(make_config(strategy="nope"))
