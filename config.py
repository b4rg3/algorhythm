"""Configuration loading for algorhythm."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    """Read an environment variable as a float, falling back to a default."""
    value = os.getenv(name)
    return float(value) if value else default


def _env_int(name: str, default: int) -> int:
    """Read an environment variable as an int, falling back to a default."""
    value = os.getenv(name)
    return int(value) if value else default


@dataclass
class Config:
    """Runtime configuration for the trading bot, loaded from environment variables."""

    exchange: str = os.getenv("EXCHANGE", "kraken")
    symbol: str = os.getenv("SYMBOL", "DOGE/USDT")
    timeframe: str = os.getenv("TIMEFRAME", "15m")

    short_window: int = _env_int("SHORT_WINDOW", 9)
    long_window: int = _env_int("LONG_WINDOW", 21)
    rsi_period: int = _env_int("RSI_PERIOD", 14)
    rsi_overbought: float = _env_float("RSI_OVERBOUGHT", 70.0)
    rsi_oversold: float = _env_float("RSI_OVERSOLD", 30.0)

    paper_balance_usdt: float = _env_float("PAPER_BALANCE_USDT", 1000.0)
    risk_per_trade_pct: float = _env_float("RISK_PER_TRADE_PCT", 0.02)
    stop_loss_pct: float = _env_float("STOP_LOSS_PCT", 0.03)

    # Execution cost model (fractions, e.g. 0.004 = 0.40%). Defaults approximate
    # Kraken's entry-tier taker fee plus a small slippage allowance.
    fee_pct: float = _env_float("FEE_PCT", 0.004)
    slippage_pct: float = _env_float("SLIPPAGE_PCT", 0.0005)

    api_key: str = os.getenv("API_KEY", "")
    api_secret: str = os.getenv("API_SECRET", "")
