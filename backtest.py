"""CLI entry point for running a historical backtest."""

import argparse
import math

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from backtest.runner import Backtester
from config import Config
from data.fetcher import DataFetcher
from logger.trade_log import _price_fmt


def _pct(v: float) -> str:
    color = "green" if v >= 0 else "red"
    return f"[{color}]{v:+.2f}%[/{color}]"


def _usdt(v: float) -> str:
    color = "green" if v >= 0 else "red"
    return f"[{color}]{v:+.2f} USDT[/{color}]"


def print_report(results: dict, days: int, config: Config, df) -> None:
    console = Console()

    r = results
    pf = r["profit_factor"]
    pf_str = f"{pf:.2f}" if not math.isinf(pf) else "inf"

    # Summary table
    summary = Table(show_header=False, box=None, padding=(0, 1))
    summary.add_row("Symbol", config.symbol)
    summary.add_row("Data source", f"{config.history_exchange}  (live trading on {config.exchange})")
    summary.add_row("Timeframe", config.timeframe)
    summary.add_row(
        "Period",
        f"{df.index[0]:%Y-%m-%d %H:%M} to {df.index[-1]:%Y-%m-%d %H:%M} UTC  ({len(df)} candles)",
    )
    summary.add_row("MA windows", f"EMA {config.short_window} / {config.long_window}")
    summary.add_row("RSI period", f"{config.rsi_period}  (ob={config.rsi_overbought} os={config.rsi_oversold})")
    summary.add_row("", "")
    summary.add_row("Start balance", f"{r['start_balance']:.2f} USDT")
    summary.add_row("Final value", f"{r['final_value']:.2f} USDT")
    summary.add_row("Total return", _pct(r["total_return_pct"]))
    summary.add_row("Realized P&L", _usdt(r["total_pnl"]) + "  (net of fees)")
    summary.add_row("Fees paid", f"{r['total_fees']:.2f} USDT")
    summary.add_row(
        "Cost model",
        f"fee {config.fee_pct * 100:.2f}% / slippage {config.slippage_pct * 100:.2f}% per fill",
    )
    summary.add_row("", "")
    summary.add_row("Closed trades", f"{r['total_trades']}  ({r['stop_losses']} stop-outs)")
    summary.add_row("Wins / Losses", f"{r['wins']} / {r['losses']}")
    summary.add_row("Win rate", f"{r['win_rate']:.1f}%")
    summary.add_row("Avg win", f"{r['avg_win']:+.2f} USDT")
    summary.add_row("Avg loss", f"{r['avg_loss']:+.2f} USDT")
    summary.add_row("Profit factor", pf_str)
    summary.add_row("Max drawdown", f"{r['max_drawdown_pct']:.2f}%")
    summary.add_row("Best trade", _usdt(r["best_trade"]))
    summary.add_row("Worst trade", _usdt(r["worst_trade"]))

    if r["open_position"]:
        pos = r["open_position"]
        unrealized = (r["final_price"] - pos["entry_price"]) * pos["quantity"]
        summary.add_row("", "")
        summary.add_row(
            "Open position",
            f"BUY {pos['quantity']:.4f} @ {_price_fmt(pos['entry_price'])}  "
            f"unrealized {_usdt(unrealized)}",
        )

    console.print(Panel(summary, title=f"Backtest Results — {days}d", border_style="cyan"))

    # Trade log
    trades = [t for t in r["trade_log"] if "pnl" in t]
    if not trades:
        return

    log = Table(title="Closed Trades", header_style="bold", border_style="dim")
    log.add_column("Timestamp", style="dim")
    log.add_column("Action")
    log.add_column("Price", justify="right")
    log.add_column("Quantity", justify="right")
    log.add_column("P&L", justify="right")

    for t in trades:
        ts = str(t["ts"])[:16].replace("T", " ")
        pnl = t["pnl"]
        color = "green" if pnl >= 0 else "red"
        log.add_row(
            ts,
            f"[{color}]{t['action']}[/{color}]",
            _price_fmt(t["price"]),
            f"{t['quantity']:.4f}",
            f"[{color}]{pnl:+.2f}[/{color}]",
        )

    console.print(log)


def main() -> None:
    parser = argparse.ArgumentParser(description="algorhythm backtester")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest (default 30)")
    args = parser.parse_args()

    config = Config()
    console = Console()

    console.print(
        f"[cyan]Fetching {args.days}d of {config.symbol} {config.timeframe} candles "
        f"from {config.history_exchange}...[/cyan]"
    )
    fetcher = DataFetcher(config, exchange_id=config.history_exchange)
    try:
        df = fetcher.fetch_history(days=args.days)
    except RuntimeError as exc:
        console.print(f"[bold red]ERROR:[/bold red] {exc}")
        raise SystemExit(1)
    console.print(f"[dim]  {len(df)} candles fetched.[/dim]")

    console.print("[cyan]Running backtest...[/cyan]")
    bt = Backtester(config)
    results = bt.run(df)

    print_report(results, args.days, config, df)


if __name__ == "__main__":
    main()
