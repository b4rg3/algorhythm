"""Protocol step 1: choose the timeframe from trading costs vs typical price movement.

Uses the TRAIN segment only and computes no strategy returns, just volatility (ATR).
Writes the decision to research/<version>/timeframe_choice.json.
"""

import os

import pandas_ta as ta
from rich.console import Console
from rich.table import Table

from data.fetcher import DataFetcher
from research import protocol as P


def main() -> None:
    console = Console()
    base = P.base_config()
    sp = P.splits()
    cost = P.round_trip_cost_pct(base)
    threshold = P.ATR_COST_MULTIPLE * cost
    train_days = (sp.validation_start - sp.start).days

    console.print(
        f"[cyan]Protocol {P.VERSION} step 1: train segment {sp.start:%Y-%m-%d} to "
        f"{sp.validation_start:%Y-%m-%d}, round-trip cost {cost:.2f}%, "
        f"threshold median ATR({P.ATR_PERIOD}) >= {threshold:.2f}%[/cyan]"
    )

    stats = []
    for tf in P.TIMEFRAME_CANDIDATES:
        cfg = replace(base, timeframe=tf)
        df = DataFetcher(cfg, exchange_id=base.history_exchange).fetch_history(
            days=train_days, end=sp.validation_start
        )
        atr_pct = ta.atr(df["high"], df["low"], df["close"], length=P.ATR_PERIOD) / df["close"] * 100
        abs_move = df["close"].pct_change().abs() * 100
        stats.append({
            "timeframe": tf,
            "candles": len(df),
            "median_atr_pct": float(atr_pct.median()),
            "median_abs_close_move_pct": float(abs_move.median()),
            "atr_to_cost": float(atr_pct.median() / cost),
            "passes": bool(atr_pct.median() >= threshold),
        })
        console.print(f"  [dim]{tf}: {len(df)} candles[/dim]")

    chosen = next((s["timeframe"] for s in stats if s["passes"]), None)

    table = Table(title="Typical candle movement vs round-trip cost (train segment)", header_style="bold")
    for col in ["Timeframe", "Candles", "Median ATR%", "Median |move|%", "ATR / cost", "Passes"]:
        table.add_column(col, justify="right" if col != "Timeframe" else "left")
    for s in stats:
        mark = "[green]yes[/green]" if s["passes"] else "[red]no[/red]"
        if s["timeframe"] == chosen:
            mark += "  <- chosen"
        table.add_row(
            s["timeframe"], str(s["candles"]), f"{s['median_atr_pct']:.2f}",
            f"{s['median_abs_close_move_pct']:.2f}", f"{s['atr_to_cost']:.2f}x", mark,
        )
    console.print(table)

    P.save_json(P.TIMEFRAME_CHOICE_PATH, {
        "protocol": P.VERSION,
        "symbol": base.symbol,
        "rule": f"fastest timeframe with median ATR({P.ATR_PERIOD})% >= "
        f"{P.ATR_COST_MULTIPLE} x round-trip cost ({threshold:.2f}%)",
        "round_trip_cost_pct": cost,
        "train_segment": [sp.start, sp.validation_start],
        "stats": stats,
        "chosen": chosen,
    })
    if chosen:
        console.print(f"[bold green]Chosen timeframe: {chosen}[/bold green]  (saved to {os.path.relpath(P.TIMEFRAME_CHOICE_PATH)})")
    else:
        console.print("[bold red]No timeframe meets the rule.[/bold red]")


if __name__ == "__main__":
    main()
