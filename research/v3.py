"""Research protocol v3 (see RESEARCH.md): daily SMA trend-following on BTC, ETH and DOGE.

The constants below are the pre-registered rules. Changing them after results have been
seen means starting a new protocol version.
"""

import os
from dataclasses import replace

import pandas as pd

from config import Config

VERSION = "v3"

MARKETS = {"BTC/USDT": "bitcoin", "ETH/USDT": "ethereum", "DOGE/USDT": "dogecoin"}
HISTORY_EXCHANGE = "gate"
TIMEFRAME = "1d"

DATA_START = pd.Timestamp("2019-05-01", tz="UTC")  # warm-up before training starts
TRAIN_START = pd.Timestamp("2020-01-01", tz="UTC")
VALIDATION_START = pd.Timestamp("2024-01-01", tz="UTC")
HOLDOUT_START = pd.Timestamp("2026-08-13", tz="UTC")
HOLDOUT_END = pd.Timestamp("2026-11-11", tz="UTC")

GRID_SMA = [50, 100, 150, 200]
GRID_BAND = [0.0, 0.02]

MIN_TRAIN_TRADES = 5
MIN_POSITIVE_MARKETS = 2

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), VERSION)
SELECTION_PATH = os.path.join(RESEARCH_DIR, "selection.json")


def config_for(symbol: str, variant: dict) -> Config:
    """Config for one market and variant under v3's fixed execution rules."""
    return replace(
        Config(),
        symbol=symbol,
        coingecko_id=MARKETS[symbol],
        history_exchange=HISTORY_EXCHANGE,
        timeframe=TIMEFRAME,
        strategy="trend",
        trend_sma_period=variant["sma"],
        trend_band=variant["band"],
        sizing_mode="allocation",
        allocation_pct=1.0,
        use_stop_loss=False,
    )


def grid() -> list[dict]:
    """The 8 pre-declared variants."""
    return [{"sma": n, "band": b} for n in GRID_SMA for b in GRID_BAND]


def label(v: dict) -> str:
    return f"SMA{v['sma']} band{v['band'] * 100:.0f}%"


def neighbours(v: dict) -> list[dict]:
    """Adjacent SMA lengths with the same band."""
    i = GRID_SMA.index(v["sma"])
    return [{"sma": GRID_SMA[j], "band": v["band"]} for j in (i - 1, i + 1) if 0 <= j < len(GRID_SMA)]
