"""Daily SMA trend-following strategy (research protocol v3)."""

import pandas as pd

from config import Config


class TrendStrategy:
    """Long while price is above its SMA, cash while below, with a hysteresis band.

    BUY  when close > SMA(N) * (1 + band)
    SELL when close < SMA(N) * (1 - band)
    HOLD otherwise (the trader ignores BUY while long and SELL while flat, so the
    band behaves as hysteresis: the position only flips once price clears it).
    """

    def __init__(self, config: Config) -> None:
        self.config = config

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add the SMA column and drop warm-up rows."""
        df = df.copy()
        df["sma"] = df["close"].rolling(self.config.trend_sma_period).mean()
        return df.dropna(subset=["sma"])

    def signal(self, df: pd.DataFrame) -> str:
        """Return the signal for the most recent completed candle."""
        if df.empty:
            return "HOLD"
        last = df.iloc[-1]
        band = self.config.trend_band
        if last["close"] > last["sma"] * (1 + band):
            return "BUY"
        if last["close"] < last["sma"] * (1 - band):
            return "SELL"
        return "HOLD"

    def describe(self, df: pd.DataFrame) -> dict:
        """Return current indicator values and the resulting signal."""
        last = df.iloc[-1]
        return {
            "close": last["close"],
            f"sma{self.config.trend_sma_period}": last["sma"],
            "band": self.config.trend_band,
            "signal": self.signal(df),
        }
