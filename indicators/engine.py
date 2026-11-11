"""Technical indicator calculations."""

import pandas as pd
import pandas_ta as ta

from config import Config


class IndicatorEngine:
    """Computes moving average and RSI indicators, plus crossover signals."""

    def __init__(self, config: Config) -> None:
        """Store the strategy configuration."""
        self.config = config

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add SMA/EMA/RSI and crossover columns to the OHLCV dataframe."""
        df = df.copy()

        df["sma_short"] = ta.sma(df["close"], length=self.config.short_window)
        df["sma_long"] = ta.sma(df["close"], length=self.config.long_window)
        df["ema_short"] = ta.ema(df["close"], length=self.config.short_window)
        df["ema_long"] = ta.ema(df["close"], length=self.config.long_window)
        df["rsi"] = ta.rsi(df["close"], length=self.config.rsi_period)

        required = ["sma_short", "sma_long", "ema_short", "ema_long", "rsi"]
        if self.config.trend_period > 0:
            df["trend_ma"] = ta.ema(df["close"], length=self.config.trend_period)
            required.append("trend_ma")

        short_above_long = df["ema_short"] > df["ema_long"]
        prev_short_above_long = short_above_long.shift(1, fill_value=False)

        df["crossover"] = 0
        df.loc[short_above_long & ~prev_short_above_long, "crossover"] = 1
        df.loc[~short_above_long & prev_short_above_long, "crossover"] = -1

        return df.dropna(subset=required)
