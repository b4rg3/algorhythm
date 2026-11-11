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

    def __init__(self, config: Config, exchange_id: str | None = None) -> None:
        """Create a fetcher for `exchange_id` (defaults to the live trading exchange)."""
        self.config = config
        self.exchange_id = exchange_id or config.exchange
        exchange_class = getattr(ccxt, self.exchange_id)
        self.exchange = exchange_class({"enableRateLimit": True})

    def fetch_candles(self, limit: int = 100) -> pd.DataFrame:
        """Fetch the most recent OHLCV candles as a UTC-indexed DataFrame."""
        try:
            raw = self.exchange.fetch_ohlcv(
                self.config.symbol, timeframe=self.config.timeframe, limit=limit
            )
        except ccxt.BaseError as exc:
            raise RuntimeError(f"Failed to fetch OHLCV data from {self.exchange_id}: {exc}") from exc

        return self._drop_incomplete(self._to_dataframe(raw))

    def fetch_history(self, days: int = 30, end: pd.Timestamp | None = None) -> pd.DataFrame:
        """Fetch paginated OHLCV history covering the `days` calendar days before `end`.

        `end` defaults to now. Pass a fixed `end` for reproducible research windows.
        Raises if the exchange can't serve the requested range (e.g. Kraken, which
        silently returns only its latest 720 candles regardless of `since`).
        """
        minutes = _TF_MINUTES.get(self.config.timeframe, 15)
        tf_ms = minutes * 60 * 1000
        per_request = 300  # within every supported exchange's page limit (Coinbase is 300)

        now_ms = int(time.time() * 1000)
        end_ms = min(int(end.timestamp() * 1000), now_ms) if end is not None else now_ms
        start_ms = end_ms - days * 86_400_000
        since_ms = start_ms

        all_raw: list = []
        while since_ms < end_ms:
            try:
                batch = self.exchange.fetch_ohlcv(
                    self.config.symbol,
                    timeframe=self.config.timeframe,
                    since=since_ms,
                    limit=per_request,
                )
            except ccxt.BaseError as exc:
                raise RuntimeError(
                    f"Failed to fetch OHLCV history from {self.exchange_id}: {exc}"
                ) from exc

            if not batch:
                break

            all_raw.extend(batch)
            next_since = batch[-1][0] + tf_ms
            if next_since <= since_ms:
                break  # exchange isn't advancing; avoid an infinite loop
            since_ms = next_since

        if not all_raw:
            raise RuntimeError(f"No historical data returned by {self.exchange_id}.")

        df = self._to_dataframe(all_raw)
        df = df[~df.index.duplicated(keep="last")]
        df = df[df.index >= pd.Timestamp(start_ms, unit="ms", tz="UTC")]
        # Keep only candles that closed by `end`.
        df = df[df.index + pd.Timedelta(minutes=minutes) <= pd.Timestamp(end_ms, unit="ms", tz="UTC")]
        df.sort_index(inplace=True)
        if df.empty:
            raise RuntimeError(f"No historical data returned by {self.exchange_id} in the requested window.")

        # Coverage check: the first candle should be near the requested start.
        first_ms = int(df.index[0].timestamp() * 1000)
        if first_ms - start_ms > 2 * tf_ms:
            got_days = (end_ms - first_ms) / 86_400_000
            raise RuntimeError(
                f"{self.exchange_id} only returned {got_days:.1f} of the {days} requested days "
                f"(first candle {df.index[0]:%Y-%m-%d %H:%M} UTC). "
                "Set HISTORY_EXCHANGE to an exchange with deeper history, or reduce --days."
            )

        return self._drop_incomplete(df)

    def _drop_incomplete(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop the last candle if it is still forming (its close time is in the future)."""
        if df.empty:
            return df
        minutes = _TF_MINUTES.get(self.config.timeframe, 15)
        close_time = df.index[-1] + pd.Timedelta(minutes=minutes)
        if close_time > pd.Timestamp.now(tz="UTC"):
            return df.iloc[:-1]
        return df

    def _to_dataframe(self, raw: list) -> pd.DataFrame:
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df
