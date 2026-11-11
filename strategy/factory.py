"""Build the configured strategy."""

from config import Config
from strategy.ma_rsi import MARSIStrategy
from strategy.trend import TrendStrategy

STRATEGIES = {"ma_rsi": MARSIStrategy, "trend": TrendStrategy}


def make_strategy(config: Config):
    """Return the strategy named by config.strategy."""
    try:
        return STRATEGIES[config.strategy](config)
    except KeyError:
        raise ValueError(f"Unknown STRATEGY '{config.strategy}'; choose from {sorted(STRATEGIES)}") from None
