"""Entry point for the algorhythm paper trading bot."""

import time

import schedule
from rich.console import Console
from rich.panel import Panel

from config import Config
from data.fetcher import DataFetcher
from execution.paper_trader import PaperTrader
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


def run_cycle() -> None:
    """Fetch data, compute indicators, evaluate the strategy, and execute trades."""
    try:
        df = fetcher.fetch_candles()
        df = engine.calculate(df)

        if df.empty:
            logger.log_error("No indicator data available yet.")
            return

        signal = strategy.signal(df)
        indicators = strategy.describe(df)
        price = df.iloc[-1]["close"]

        logger.log_candle(indicators)

        trade = trader.execute(signal, price, risk_manager)
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
    banner = (
        "[bold cyan]algorhythm[/bold cyan] - MA crossover + RSI paper trading bot\n\n"
        f"Symbol:          {config.symbol}\n"
        f"Timeframe:       {config.timeframe}\n"
        f"Starting balance: {config.paper_balance_usdt:.2f} USDT\n"
        f"MA windows:      short={config.short_window}, long={config.long_window}"
    )
    console.print(Panel(banner, title="Startup", border_style="cyan"))


if __name__ == "__main__":
    print_banner()

    run_cycle()

    schedule.every(15).minutes.do(run_cycle)

    while True:
        schedule.run_pending()
        time.sleep(1)
