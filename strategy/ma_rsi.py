"""Moving average crossover + RSI trading strategy."""

import pandas as pd

from config import Config


class MARSIStrategy:
    """Generates BUY/SELL/HOLD signals from MA crossover and RSI indicators."""

    def __init__(self, config: Config) -> None:
        """Store the strategy configuration."""
        self.config = config

    def signal(self, df: pd.DataFrame) -> str:
        """Return the trading signal for the most recent completed candle."""
        if len(df) < 2:
            return "HOLD"

        last = df.iloc[-1]
        cfg = self.config

        # Trend filter: new longs only while price is above the long-term EMA.
        uptrend = cfg.trend_period <= 0 or last["close"] > last["trend_ma"]

        if cfg.rsi_oversold_buy and uptrend and last["rsi"] < cfg.rsi_oversold:
            return "BUY"
        if last["crossover"] == -1 or last["rsi"] > cfg.rsi_overbought:
            return "SELL"
        if uptrend and last["crossover"] == 1 and last["rsi"] < cfg.rsi_overbought:
            return "BUY"
        return "HOLD"

    def describe(self, df: pd.DataFrame) -> dict:
        """Return a dict of current indicator values and the resulting signal."""
        last = df.iloc[-1]
        return {
            "sma_short": last["sma_short"],
            "sma_long": last["sma_long"],
            "ema_short": last["ema_short"],
            "ema_long": last["ema_long"],
            "rsi": last["rsi"],
            "crossover": last["crossover"],
            "trend_ma": last.get("trend_ma"),
            "signal": self.signal(df),
        }
