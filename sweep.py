"""Protocol steps 2-3: run the fixed variant grid on train + validation, apply the selection rule.

Never loads holdout data. The timeframe comes from research/timeframe_choice.json (step 1).
Writes every result and the selection to research/<version>/selection.json.
"""

import math
import os
from dataclasses import replace

from rich.console import Console
from rich.table import Table

from backtest.runner import Backtester
from data.coingecko import cross_check
from data.fetcher import DataFetcher
from research import protocol as P


def _pct(v: float) -> str:
    color = "green" if v > 0 else "red"
    return f"[{color}]{v:+.1f}%[/{color}]"


def _pf(v: float) -> str:
    return "inf" if math.isinf(v) else f"{v:.2f}"


def _key(v: dict) -> tuple:
    return (v["short_window"], v["long_window"], v["trend_period"], v["rsi_oversold_buy"])


def main() -> None:
    console = Console()
    choice = P.load_json(P.TIMEFRAME_CHOICE_PATH)
    tf = choice["chosen"]
    if not tf:
        raise SystemExit("Step 1 chose no timeframe; nothing to sweep.")

    sp = P.splits()
    base = P.base_config(timeframe=tf)
    pre_holdout_days = (sp.holdout_start - sp.start).days

    console.print(
        f"[cyan]Protocol {P.VERSION} steps 2-3 on {base.symbol} {tf}: "
        f"train {sp.start:%Y-%m-%d} to {sp.validation_start:%Y-%m-%d}, "
        f"validation to {sp.holdout_start:%Y-%m-%d} (holdout not loaded)[/cyan]"
    )
    df = DataFetcher(base, exchange_id=base.history_exchange).fetch_history(
        days=pre_holdout_days, end=sp.holdout_start
    )
    console.print(f"[dim]  {len(df)} candles[/dim]")

    try:
        check = cross_check(df, base.coingecko_id, tf)
        color = "green" if check.ok else "bold red"
        console.print(f"[{color}]CoinGecko cross-check (overlapping span) {check.summary()}[/{color}]")
        if not check.ok:
            raise SystemExit("Exchange data doesn't track CoinGecko; aborting.")
    except RuntimeError as exc:
        console.print(f"[yellow]CoinGecko cross-check unavailable: {exc}[/yellow]")

    rows = []
    for v in P.grid():
        bt = Backtester(replace(base, **v))
        train = bt.run(df, end=sp.validation_start)
        val = bt.run(df, start=sp.validation_start)
        rows.append({
            "variant": v,
            "label": P.variant_label(v),
            "train": {k: train[k] for k in ("total_return_pct", "total_trades", "profit_factor", "max_drawdown_pct", "buy_hold_pct")},
            "validation": {k: val[k] for k in ("total_return_pct", "total_trades", "profit_factor", "max_drawdown_pct", "buy_hold_pct")},
        })

    # --- Selection rule (RESEARCH.md step 3) ---
    survivors = [r for r in rows if r["train"]["total_return_pct"] > 0]
    selected = max(survivors, key=lambda r: r["validation"]["total_return_pct"], default=None)

    status = "selected"
    reason = ""
    fragility = None
    if selected is None:
        status, reason = "rejected", "no variant had a positive train return"
    elif selected["validation"]["total_return_pct"] <= 0:
        status, reason = "rejected", "best surviving variant had a non-positive validation return"
    else:
        by_key = {_key(r["variant"]): r for r in rows}
        nbrs = [by_key[_key(n)] for n in P.neighbours(selected["variant"])]
        positive = sum(1 for n in nbrs if n["validation"]["total_return_pct"] > 0)
        fragility = {"neighbours": len(nbrs), "positive_on_validation": positive, "fragile": positive == 0}

    # --- Report ---
    table = Table(
        title=f"{tf} variants (sorted by train return); fee {base.fee_pct * 100:.2f}% + slip "
        f"{base.slippage_pct * 100:.2f}% per fill",
        header_style="bold",
    )
    for col in ["Variant", "Train ret", "Trades", "PF", "MaxDD", "Val ret", "Trades", "PF", "MaxDD"]:
        table.add_column(col, justify="left" if col == "Variant" else "right")
    for r in sorted(rows, key=lambda r: r["train"]["total_return_pct"], reverse=True):
        t, v = r["train"], r["validation"]
        label = r["label"] + ("  <- selected" if selected is r and status == "selected" else "")
        table.add_row(
            label, _pct(t["total_return_pct"]), str(t["total_trades"]), _pf(t["profit_factor"]),
            f"{t['max_drawdown_pct']:.1f}%", _pct(v["total_return_pct"]), str(v["total_trades"]),
            _pf(v["profit_factor"]), f"{v['max_drawdown_pct']:.1f}%",
        )
    console.print(table)
    console.print(
        f"Buy & hold: train {_pct(rows[0]['train']['buy_hold_pct'])}, "
        f"validation {_pct(rows[0]['validation']['buy_hold_pct'])}"
    )
    console.print(f"{len(survivors)} of {len(rows)} variants had a positive train return.")

    if status == "selected":
        console.print(f"[bold green]Selected: {selected['label']}[/bold green]")
        console.print(
            f"Neighbours positive on validation: {fragility['positive_on_validation']}/{fragility['neighbours']}"
            + ("  [bold red](FRAGILE)[/bold red]" if fragility["fragile"] else "")
        )
    else:
        console.print(f"[bold red]Strategy rejected: {reason}. Holdout will not be run.[/bold red]")

    P.save_json(P.SELECTION_PATH, {
        "protocol": P.VERSION,
        "symbol": base.symbol,
        "timeframe": tf,
        "status": status,
        "reason": reason,
        "selected": selected["variant"] if status == "selected" else None,
        "fragility": fragility,
        "results": rows,
    })
    console.print(f"[dim]Saved to {os.path.relpath(P.SELECTION_PATH)}[/dim]")


if __name__ == "__main__":
    main()
