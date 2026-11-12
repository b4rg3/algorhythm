"""F1 forward paper test (RESEARCH.md): the registered rules, as constants."""

import os
from dataclasses import replace

import pandas as pd

from config import Config
from research import v3

VERSION = "F1"
REGISTERED_AT = pd.Timestamp("2026-11-12 00:05:18", tz="UTC")  # commit 55007ea

SYMBOLS = list(v3.MARKETS)
VARIANT = {"sma": 100, "band": 0.02}  # v3's selected rule, frozen
EXCHANGE = "kraken"
CANDLE = pd.Timedelta(days=1)
FETCH_LIMIT = 310  # Kraken daily candles; >3x the SMA length for warm-up

CHECKPOINT_WEEKS = 26
FINAL_WEEKS = 104
CONSISTENCY_FLOOR_PP = -22.0
MIN_WEEKS_EACH_WAY = 10
FIDELITY_PRICE_TOL = 0.001
MAX_MISSED = {"checkpoint": 5, "final": 20}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "f1")


def config_for(symbol: str) -> Config:
    """v3's registered execution rules on Kraken, with everything pinned (ignores .env)."""
    return replace(
        v3.config_for(symbol, VARIANT),
        exchange=EXCHANGE,
        paper_balance_usdt=1000.0,
        fee_pct=0.004,
        slippage_pct=0.0005,
    )


def start_candle(registered_at: pd.Timestamp = REGISTERED_AT) -> pd.Timestamp:
    """Open time of the first daily candle that closes after registration."""
    first_open = registered_at.floor("D")
    return first_open if first_open + CANDLE > registered_at else first_open + CANDLE


def symbol_dir(symbol: str, base: str = DATA_DIR) -> str:
    return os.path.join(base, symbol.replace("/", "_"))
