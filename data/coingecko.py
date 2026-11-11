"""Cross-check exchange OHLCV data against CoinGecko's aggregated market price.

CoinGecko's price is a volume-weighted blend across many exchanges, quoted in USD, so it
won't match a single USDT venue exactly — but a healthy exchange feed should stay within a
fraction of a percent of it. Large or persistent deviations point at bad data (wrong
symbol, stale candles, gaps, a thin or broken market) that would invalidate a backtest.

Uses the public REST API (no key needed). If COINGECKO_API_KEY is set it is sent as a
Demo API key for higher rate limits.
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import pandas as pd

_BASE = "https://api.coingecko.com/api/v3"
_CHUNK_DAYS = 90  # ranges up to 90 days come back at hourly granularity

_TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
}


@dataclass
class CrossCheck:
    """Summary of how closely exchange closes track CoinGecko's price."""

    points: int
    median_abs_pct: float
    p95_abs_pct: float
    max_abs_pct: float
    exchange_change_pct: float
    coingecko_change_pct: float

    @property
    def ok(self) -> bool:
        return self.points >= 10 and self.median_abs_pct < 1.0 and self.p95_abs_pct < 3.0

    def summary(self) -> str:
        status = "OK" if self.ok else "MISMATCH"
        return (
            f"{status}: {self.points} points, deviation median {self.median_abs_pct:.2f}% / "
            f"p95 {self.p95_abs_pct:.2f}% / max {self.max_abs_pct:.2f}%; "
            f"period change exchange {self.exchange_change_pct:+.1f}% vs "
            f"CoinGecko {self.coingecko_change_pct:+.1f}%"
        )


def _get(path: str, params: dict) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{_BASE}{path}?{query}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "algorhythm-backtester")
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        req.add_header("x-cg-demo-api-key", api_key)

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(15 * (attempt + 1))  # public tier rate limit; back off
                continue
            raise RuntimeError(f"CoinGecko request failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"CoinGecko request failed: {exc.reason}") from exc
    raise RuntimeError("CoinGecko request failed after retries")


def fetch_prices(coin_id: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Return CoinGecko USD prices between start and end (hourly where available).

    The keyless public API only serves the last 365 days, so older ranges are clipped.
    """
    if not os.getenv("COINGECKO_API_KEY"):
        oldest = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=364)
        start = max(start, oldest)
        if start >= end:
            raise RuntimeError("the public CoinGecko API only serves the last 365 days")
    points: list = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + pd.Timedelta(days=_CHUNK_DAYS), end)
        data = _get(
            f"/coins/{coin_id}/market_chart/range",
            {
                "vs_currency": "usd",
                "from": int(chunk_start.timestamp()),
                "to": int(chunk_end.timestamp()),
            },
        )
        points.extend(data.get("prices", []))
        chunk_start = chunk_end
        if chunk_start < end:
            time.sleep(2)

    if not points:
        raise RuntimeError(f"CoinGecko returned no prices for '{coin_id}'.")

    s = pd.Series(
        [p[1] for p in points],
        index=pd.to_datetime([p[0] for p in points], unit="ms", utc=True),
        name="cg_price",
    )
    return s[~s.index.duplicated()].sort_index()


def cross_check(df: pd.DataFrame, coin_id: str, timeframe: str) -> CrossCheck:
    """Compare an exchange OHLCV DataFrame's closes with CoinGecko prices."""
    tf = pd.Timedelta(minutes=_TF_MINUTES.get(timeframe, 15))

    # A candle's close is the price at the END of its interval.
    ex = pd.DataFrame({"ex_close": df["close"].values}, index=df.index + tf)
    cg = fetch_prices(coin_id, df.index[0], df.index[-1] + tf).to_frame()

    merged = pd.merge_asof(
        cg.sort_index(),
        ex.sort_index(),
        left_index=True,
        right_index=True,
        direction="nearest",
        tolerance=tf,
    ).dropna()
    if merged.empty:
        raise RuntimeError("No overlapping timestamps between exchange data and CoinGecko.")

    dev = ((merged["ex_close"] - merged["cg_price"]) / merged["cg_price"]).abs() * 100

    return CrossCheck(
        points=len(merged),
        median_abs_pct=float(dev.median()),
        p95_abs_pct=float(dev.quantile(0.95)),
        max_abs_pct=float(dev.max()),
        exchange_change_pct=float(merged["ex_close"].iloc[-1] / merged["ex_close"].iloc[0] - 1) * 100,
        coingecko_change_pct=float(merged["cg_price"].iloc[-1] / merged["cg_price"].iloc[0] - 1) * 100,
    )
