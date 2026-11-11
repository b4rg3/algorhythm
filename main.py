"""Entry point for the algorhythm paper trading bot."""

import os
import time

import schedule
from rich.console import Console
from rich.panel import Panel

from config import Config
from data.fetcher import DataFetcher
from execution.paper_trader import PaperTrader, STATE_PATH
from indicators.engine import IndicatorEngine
from logger.trade_log import TradeLogger
from risk.manager import RiskManager
from strategy.ma_rsi import MARSIStrategy

config = Config()
fetcher = DataFetcher(config)
engine = IndicatorEngine(config)
strategy = MARSIStrategy(config)
risk_manager = RiskManager(config)
trader = PaperTrader(config)
logger = TradeLogger()

# Enough history for the slowest indicator to warm up (EMAs need several multiples of their
# length to converge). Kraken serves at most 720 candles.
CANDLE_LIMIT = min(720, 3 * max(config.long_window, config.trend_period, config.rsi_period) + 10)


def run_cycle() -> None:
    """Fetch data, compute indicators, evaluate the strategy, and execute trades."""
    try:
        df = fetcher.fetch_candles(limit=CANDLE_LIMIT)
        df = engine.calculate(df)

        if df.empty:
            logger.log_error("No indicator data available yet.")
            return

        candle = df.iloc[-1]
        candle_ts = df.index[-1]
        price = candle["close"]

        if trader.already_processed(candle_ts):
            # No new completed candle since the last cycle; don't act on the same one twice.
            return

        signal = strategy.signal(df)
        indicators = strategy.describe(df)

        logger.log_candle(indicators)

        trade = trader.execute(signal, candle, risk_manager, candle_ts=candle_ts)
        if trade is not None:
            logger.log_trade(trade)

        logger.log_portfolio(
            trader.portfolio_value(price),
            trader.balance_usdt,
            trader.balance_base,
            price,
        )
    except Exception as exc:
        logger.log_error(str(exc))


def print_banner() -> None:
    """Print a startup banner with the current run configuration."""
    console = Console()
    resumed = os.path.exists(STATE_PATH)
    balance_label = "Resumed balance" if resumed else "Starting balance"
    balance_value = trader.balance_usdt if resumed else config.paper_balance_usdt
    banner = (
        "[bold cyan]algorhythm[/bold cyan] - MA crossover + RSI paper trading bot\n\n"
        f"Symbol:           {config.symbol}\n"
        f"Timeframe:        {config.timeframe}\n"
        f"{balance_label}: {balance_value:.2f} USDT\n"
        f"MA windows:       short={config.short_window}, long={config.long_window}\n"
        f"State:            {'resumed from ' + STATE_PATH if resumed else 'fresh start'}"
    )
    console.print(Panel(banner, title="Startup", border_style="cyan"))


if __name__ == "__main__":
    print_banner()

    resumed = os.path.exists(STATE_PATH)
    logger.log_session_start(config, trader.balance_usdt, resumed)

    run_cycle()

    # Poll every minute; run_cycle only acts when a new candle has closed, so this works
    # for any TIMEFRAME and reacts within a minute of each candle close.
    schedule.every(1).minutes.do(run_cycle)

    while True:
        schedule.run_pending()
        time.sleep(1)
