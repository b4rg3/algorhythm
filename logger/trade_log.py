"""Rich-formatted console logging for candles, trades, and portfolio state."""

import math

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _price_fmt(price: float) -> str:
    """Format a price with enough decimal places to show at least 4 significant figures."""
    if price == 0:
        return "0.00"
    decimals = max(2, -int(math.floor(math.log10(abs(price)))) + 3)
    return f"{price:.{decimals}f}"


class TradeLogger:
    """Prints formatted candle, trade, portfolio, and error output using rich."""

    def __init__(self) -> None:
        """Initialise the rich console."""
        self.console = Console()

    def log_candle(self, indicators: dict) -> None:
        """Print a compact, color-coded one-line summary of current indicators."""
        signal = indicators.get("signal", "HOLD")
        color = {"BUY": "green", "SELL": "red"}.get(signal, "dim")

        p = _price_fmt
        line = (
            f"[{color}]{signal:<4}[/{color}] "
            f"sma_short={p(indicators['sma_short'])} "
            f"sma_long={p(indicators['sma_long'])} "
            f"ema_short={p(indicators['ema_short'])} "
            f"ema_long={p(indicators['ema_long'])} "
            f"rsi={indicators['rsi']:.2f} "
            f"crossover={indicators['crossover']}"
        )
        self.console.print(line)

    def log_trade(self, trade: dict) -> None:
        """Print a rich panel summarizing a trade that was executed."""
        action = trade["action"]
        color = "green" if action == "BUY" else "red"

        p = _price_fmt
        table = Table(show_header=False, box=None)
        table.add_row("Price", p(trade["price"]))
        table.add_row("Quantity", f"{trade['quantity']:.6f}")
        if "stop_loss" in trade:
            table.add_row("Stop Loss", p(trade["stop_loss"]))
        if "pnl" in trade:
            pnl_color = "green" if trade["pnl"] >= 0 else "red"
            table.add_row("P&L", f"[{pnl_color}]{trade['pnl']:.2f}[/{pnl_color}]")
        table.add_row("Balance USDT", f"{trade['balance_usdt']:.2f}")
        table.add_row("Balance Base", f"{trade['balance_base']:.6f}")

        self.console.print(Panel(table, title=f"[{color}]{action}[/{color}]", border_style=color))

    def log_portfolio(
        self, value: float, balance_usdt: float, balance_base: float, price: float
    ) -> None:
        """Print a one-line portfolio value summary."""
        self.console.print(
            f"[bold cyan]Portfolio[/bold cyan] value={value:.2f} USDT "
            f"(usdt={balance_usdt:.2f}, base={balance_base:.6f} @ {_price_fmt(price)})"
        )

    def log_error(self, msg: str) -> None:
        """Print an error message in red."""
        self.console.print(f"[bold red]ERROR:[/bold red] {msg}")
