"""Market data fetching via ccxt."""

import ccxt
import pandas as pd

from config import Config


class DataFetcher:
    """Fetches public OHLCV candle data from a crypto exchange via ccxt."""

    def __init__(self, config: Config) -> None:
        """Store config and initialise the ccxt exchange instance."""
        self.config = config
        exchange_class = getattr(ccxt, config.exchange)
        self.exchange = exchange_class({"enableRateLimit": True})

    def fetch_candles(self, limit: int = 100) -> pd.DataFrame:
        """Fetch the most recent OHLCV candles as a UTC-indexed DataFrame."""
        try:
            raw = self.exchange.fetch_ohlcv(
                self.config.symbol, timeframe=self.config.timeframe, limit=limit
            )
        except ccxt.BaseError as exc:
            raise RuntimeError(f"Failed to fetch OHLCV data from {self.config.exchange}: {exc}") from exc

        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
