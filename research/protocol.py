"""Research protocols: the fixed rules described in RESEARCH.md, in code.

Changing anything here after results have been seen means starting a new protocol version.
Versions differ only in the market listed in PROTOCOLS; every other rule is shared.
Select a version with the PROTOCOL environment variable (default: the latest).
"""

import itertools
import json
import os
from dataclasses import dataclass, replace

import pandas as pd

from config import Config

PROTOCOLS = {
    "v1": {"symbol": "DOGE/USDT", "coingecko_id": "dogecoin"},
    "v2": {"symbol": "ETH/USDT", "coingecko_id": "ethereum"},
}

VERSION = os.getenv("PROTOCOL", "v2")
if VERSION not in PROTOCOLS:
    raise SystemExit(f"Unknown PROTOCOL '{VERSION}'; choose from {sorted(PROTOCOLS)}")
SYMBOL = PROTOCOLS[VERSION]["symbol"]
COINGECKO_ID = PROTOCOLS[VERSION]["coingecko_id"]


def base_config(**overrides) -> Config:
    """Config for this protocol's market, ignoring SYMBOL/COINGECKO_ID from the environment."""
    return replace(Config(), symbol=SYMBOL, coingecko_id=COINGECKO_ID, **overrides)

DATA_END = pd.Timestamp("2026-11-11 00:00", tz="UTC")
HISTORY_DAYS = 730
HOLDOUT_DAYS = 90
TRAIN_FRACTION = 0.70

TIMEFRAME_CANDIDATES = ["15m", "30m", "1h", "2h", "4h", "1d"]
ATR_PERIOD = 14
ATR_COST_MULTIPLE = 2.0  # median ATR% must be >= this × round-trip cost

GRID_MA = [(9, 21), (12, 26), (20, 50)]
GRID_TREND = [0, 100, 200]
GRID_RSI_BUY = [True, False]

RESEARCH_DIR = os.path.join(os.path.dirname(__file__), VERSION)
os.makedirs(RESEARCH_DIR, exist_ok=True)
TIMEFRAME_CHOICE_PATH = os.path.join(RESEARCH_DIR, "timeframe_choice.json")
SELECTION_PATH = os.path.join(RESEARCH_DIR, "selection.json")
# One shared log across versions, so every use of any holdout is on record.
HOLDOUT_LOG_PATH = os.path.join(os.path.dirname(__file__), "holdout_log.jsonl")


@dataclass(frozen=True)
class Splits:
    start: pd.Timestamp
    validation_start: pd.Timestamp
    holdout_start: pd.Timestamp
    end: pd.Timestamp


def splits() -> Splits:
    """Return the fixed segment boundaries for this protocol version."""
    start = DATA_END - pd.Timedelta(days=HISTORY_DAYS)
    holdout_start = DATA_END - pd.Timedelta(days=HOLDOUT_DAYS)
    validation_start = start + (holdout_start - start) * TRAIN_FRACTION
    return Splits(start, validation_start.floor("D"), holdout_start, DATA_END)


def round_trip_cost_pct(config) -> float:
    return 2 * (config.fee_pct + config.slippage_pct) * 100


def grid() -> list[dict]:
    """The 18 pre-declared strategy variants."""
    return [
        {"short_window": s, "long_window": l, "trend_period": t, "rsi_oversold_buy": r}
        for (s, l), t, r in itertools.product(GRID_MA, GRID_TREND, GRID_RSI_BUY)
    ]


def variant_label(v: dict) -> str:
    trend = f"trend{v['trend_period']}" if v["trend_period"] else "notrend"
    rsi = "rsibuy" if v["rsi_oversold_buy"] else "norsibuy"
    return f"ema{v['short_window']}/{v['long_window']} {trend} {rsi}"


def neighbours(v: dict) -> list[dict]:
    """Grid variants differing from `v` in exactly one setting by one step."""
    out = []
    ma_i = GRID_MA.index((v["short_window"], v["long_window"]))
    for j in (ma_i - 1, ma_i + 1):
        if 0 <= j < len(GRID_MA):
            out.append({**v, "short_window": GRID_MA[j][0], "long_window": GRID_MA[j][1]})
    t_i = GRID_TREND.index(v["trend_period"])
    for j in (t_i - 1, t_i + 1):
        if 0 <= j < len(GRID_TREND):
            out.append({**v, "trend_period": GRID_TREND[j]})
    out.append({**v, "rsi_oversold_buy": not v["rsi_oversold_buy"]})
    return out


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")
