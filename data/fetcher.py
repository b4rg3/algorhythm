"""Market data fetching via ccxt."""

import time

import ccxt
import pandas as pd

from config import Config

_TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
}


class DataFetcher:
    """Fetches public OHLCV candle data from a crypto exchange via ccxt."""

    def __init__(self, config: Config) -> None:
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

        return self._to_dataframe(raw)

    def fetch_history(self, days: int = 30) -> pd.DataFrame:
        """Fetch paginated OHLCV history covering the last `days` calendar days."""
        minutes = _TF_MINUTES.get(self.config.timeframe, 15)
        per_request = 720  # Kraken max; safe for most exchanges

        since_ms = int((time.time() - days * 86400) * 1000)
        step_ms = per_request * minutes * 60 * 1000

        all_raw: list = []
        while True:
            try:
                batch = self.exchange.fetch_ohlcv(
                    self.config.symbol,
                    timeframe=self.config.timeframe,
                    since=since_ms,
                    limit=per_request,
                )
            except ccxt.BaseError as exc:
                raise RuntimeError(f"Failed to fetch OHLCV history from {self.config.exchange}: {exc}") from exc

            if not batch:
                break

            all_raw.extend(batch)
            last_ts = batch[-1][0]
            since_ms = last_ts + minutes * 60 * 1000

            if len(batch) < per_request:
                break  # reached the present

        if not all_raw:
            raise RuntimeError("No historical data returned.")

        df = self._to_dataframe(all_raw)
        df = df[~df.index.duplicated(keep="last")]
        df.sort_index(inplace=True)
        return df

    def _to_dataframe(self, raw: list) -> pd.DataFrame:
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
