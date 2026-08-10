"""Rich-formatted console logging for candles, trades, and portfolio state."""

import json
import math
import os
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.jsonl")


def _price_fmt(price: float) -> str:
    """Format a price with enough decimal places to show at least 4 significant figures."""
    if price == 0:
        return "0.00"
    decimals = max(2, -int(math.floor(math.log10(abs(price)))) + 3)
    return f"{price:.{decimals}f}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradeLogger:
    """Prints formatted candle, trade, portfolio, and error output using rich."""

    def __init__(self) -> None:
        """Initialise the rich console."""
        self.console = Console()
        self.symbol: str = ""

    # ------------------------------------------------------------------
    # Session startup
    # ------------------------------------------------------------------

    def log_session_start(self, config, balance_usdt: float, resumed: bool) -> None:
        """Record a session-start entry and print a summary of past trades."""
        self.symbol = config.symbol
        self._append({
            "type": "session_start",
            "ts": _now(),
            "symbol": config.symbol,
            "exchange": config.exchange,
            "balance_usdt": balance_usdt,
            "resumed": resumed,
        })
        self._print_history_summary()

    # ------------------------------------------------------------------
    # Per-cycle console output
    # ------------------------------------------------------------------

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
        """Print a rich panel summarizing a trade and append it to the log file."""
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

        entry = {
            "type": "trade",
            "ts": _now(),
            "symbol": self.symbol,
            "action": action,
            "price": trade["price"],
            "quantity": trade["quantity"],
            "balance_usdt": trade["balance_usdt"],
            "balance_base": trade["balance_base"],
        }
        if "stop_loss" in trade:
            entry["stop_loss"] = trade["stop_loss"]
        if "pnl" in trade:
            entry["pnl"] = trade["pnl"]
        self._append(entry)

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

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _append(self, entry: dict) -> None:
        """Append a JSON entry as a single line to the log file."""
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _read_history(self) -> list[dict]:
        """Return all log entries from the trade log file."""
        if not os.path.exists(LOG_PATH):
            return []
        entries = []
        with open(LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def _print_history_summary(self) -> None:
        """Read the trade log and print a startup summary panel."""
        entries = self._read_history()
        trades = [e for e in entries if e.get("type") == "trade"]
        sessions = [e for e in entries if e.get("type") == "session_start"]

        if not trades:
            self.console.print(
                Panel("[dim]No previous trades on record.[/dim]", title="Trade History", border_style="cyan")
            )
            return

        closed = [t for t in trades if "pnl" in t]
        open_buys = [t for t in trades if t["action"] == "BUY" and "pnl" not in t]
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in closed)
        win_rate = len(wins) / len(closed) * 100 if closed else 0.0

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("Sessions", str(len(sessions)))
        table.add_row("Total trades", str(len(trades)))
        table.add_row("Closed", f"{len(closed)}  (W {len(wins)} / L {len(losses)})")
        table.add_row("Win rate", f"{win_rate:.1f}%")
        pnl_color = "green" if total_pnl >= 0 else "red"
        table.add_row("Realized P&L", f"[{pnl_color}]{total_pnl:+.2f} USDT[/{pnl_color}]")
        if open_buys:
            last_buy = open_buys[-1]
            table.add_row("Open position", f"BUY {last_buy['quantity']:.6f} @ {_price_fmt(last_buy['price'])}")

        # Last 5 closed trades
        if closed:
            table.add_row("", "")
            table.add_row("[bold]Recent closed trades[/bold]", "")
            for t in closed[-5:]:
                ts = t.get("ts", "")[:16].replace("T", " ")
                pnl = t["pnl"]
                c = "green" if pnl >= 0 else "red"
                table.add_row(
                    f"  {ts}",
                    f"{t['action']} {t['quantity']:.4f} @ {_price_fmt(t['price'])}  [{c}]{pnl:+.2f}[/{c}]",
                )

        self.console.print(Panel(table, title="Trade History", border_style="cyan"))
