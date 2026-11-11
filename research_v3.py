"""Run research protocol v3 (RESEARCH.md): daily SMA trend-following on BTC, ETH, DOGE.

    python research_v3.py sweep     # grid on train + validation, apply selection rule
    python research_v3.py holdout   # selected variant on the holdout, once

Results go to research/v3/ and research/holdout_log.jsonl.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from statistics import mean

from rich.console import Console
from rich.table import Table

from backtest.runner import Backtester
from data.coingecko import cross_check
from data.fetcher import DataFetcher
from research import protocol as shared
from research import v3

console = Console()
METRICS = ("total_return_pct", "total_trades", "profit_factor", "max_drawdown_pct", "buy_hold_pct", "total_fees")


def _pct(v: float) -> str:
    color = "green" if v > 0 else "red"
    return f"[{color}]{v:+.1f}%[/{color}]"


def _fetch(symbol: str, start, end):
    cfg = v3.config_for(symbol, v3.grid()[0])
    df = DataFetcher(cfg, exchange_id=v3.HISTORY_EXCHANGE).fetch_history(days=(end - start).days, end=end)
    try:
        check = cross_check(df, cfg.coingecko_id, v3.TIMEFRAME)
        color = "green" if check.ok else "bold red"
        console.print(f"  [{color}]{symbol} CoinGecko cross-check {check.summary()}[/{color}]")
        if not check.ok:
            raise SystemExit(f"{symbol} data doesn't track CoinGecko; aborting.")
    except RuntimeError as exc:
        console.print(f"  [yellow]{symbol} CoinGecko cross-check unavailable: {exc}[/yellow]")
    return df


def _pick(result: dict) -> dict:
    return {k: (result[k] if result[k] != float("inf") else "inf") for k in METRICS}


def sweep() -> None:
    console.print(
        f"[cyan]Protocol v3 sweep: train {v3.TRAIN_START:%Y-%m-%d} to {v3.VALIDATION_START:%Y-%m-%d}, "
        f"validation to {v3.HOLDOUT_START:%Y-%m-%d} (holdout not loaded), {v3.HISTORY_EXCHANGE} 1d[/cyan]"
    )
    data = {s: _fetch(s, v3.DATA_START, v3.HOLDOUT_START) for s in v3.MARKETS}

    rows = []
    for variant in v3.grid():
        per_market = {}
        for symbol, df in data.items():
            bt = Backtester(v3.config_for(symbol, variant))
            train = bt.run(df, start=v3.TRAIN_START, end=v3.VALIDATION_START)
            val = bt.run(df, start=v3.VALIDATION_START)
            per_market[symbol] = {"train": _pick(train), "validation": _pick(val)}
        train_rets = [m["train"]["total_return_pct"] for m in per_market.values()]
        val_rets = [m["validation"]["total_return_pct"] for m in per_market.values()]
        rows.append({
            "variant": variant,
            "label": v3.label(variant),
            "markets": per_market,
            "train_positive_markets": sum(r > 0 for r in train_rets),
            "train_min_trades": min(m["train"]["total_trades"] for m in per_market.values()),
            "train_mean_return": mean(train_rets),
            "validation_mean_return": mean(val_rets),
        })

    # --- Selection rule ---
    for r in rows:
        r["survives"] = (
            r["train_positive_markets"] >= v3.MIN_POSITIVE_MARKETS
            and r["train_min_trades"] >= v3.MIN_TRAIN_TRADES
        )
    survivors = [r for r in rows if r["survives"]]
    selected = max(survivors, key=lambda r: r["validation_mean_return"], default=None)

    status, reason, fragility = "selected", "", None
    if selected is None:
        status, reason = "rejected", "no variant survived the train rule"
    elif selected["validation_mean_return"] <= 0:
        status, reason = "rejected", "selected variant's mean validation return was not positive"
    else:
        by_label = {r["label"]: r for r in rows}
        nbrs = [by_label[v3.label(n)] for n in v3.neighbours(selected["variant"])]
        positive = sum(1 for n in nbrs if n["validation_mean_return"] > 0)
        fragility = {"neighbours": len(nbrs), "positive_on_validation": positive, "fragile": positive == 0}

    # --- Report ---
    symbols = list(v3.MARKETS)
    table = Table(title="v3 variants: return after costs (trades)", header_style="bold")
    table.add_column("Variant")
    for seg in ("Train", "Val"):
        for s in symbols:
            table.add_column(f"{seg} {s.split('/')[0]}", justify="right")
        table.add_column(f"{seg} mean", justify="right")
    table.add_column("Survives")
    for r in rows:
        cells = []
        for seg in ("train", "validation"):
            for s in symbols:
                m = r["markets"][s][seg]
                cells.append(f"{_pct(m['total_return_pct'])} ({m['total_trades']})")
            cells.append(_pct(r[f"{'train' if seg == 'train' else 'validation'}_mean_return"]))
        mark = "yes" if r["survives"] else "no"
        if status == "selected" and r is selected:
            mark += " <- selected"
        table.add_row(r["label"], *cells, mark)
    console.print(table)

    bh = rows[0]["markets"]
    console.print(
        "Buy & hold, train: "
        + ", ".join(f"{s.split('/')[0]} {_pct(bh[s]['train']['buy_hold_pct'])}" for s in symbols)
        + " | validation: "
        + ", ".join(f"{s.split('/')[0]} {_pct(bh[s]['validation']['buy_hold_pct'])}" for s in symbols)
    )
    console.print(
        "Max drawdown (validation): "
        + "; ".join(
            f"{r['label']}: " + ", ".join(
                f"{s.split('/')[0]} {r['markets'][s]['validation']['max_drawdown_pct']:.0f}%" for s in symbols
            )
            for r in rows
        )
    )

    if status == "selected":
        console.print(f"[bold green]Selected: {selected['label']}[/bold green]")
        console.print(
            f"Neighbours positive on validation: {fragility['positive_on_validation']}/{fragility['neighbours']}"
            + ("  [bold red](FRAGILE)[/bold red]" if fragility["fragile"] else "")
        )
    else:
        console.print(f"[bold red]Strategy rejected: {reason}. Holdout will not be run.[/bold red]")

    os.makedirs(v3.RESEARCH_DIR, exist_ok=True)
    shared.save_json(v3.SELECTION_PATH, {
        "protocol": v3.VERSION,
        "status": status,
        "reason": reason,
        "selected": selected["variant"] if status == "selected" else None,
        "fragility": fragility,
        "results": rows,
    })
    console.print(f"[dim]Saved to {os.path.relpath(v3.SELECTION_PATH)}[/dim]")


def holdout() -> None:
    if os.path.exists(shared.HOLDOUT_LOG_PATH):
        with open(shared.HOLDOUT_LOG_PATH) as f:
            prior = [json.loads(l) for l in f if l.strip() and json.loads(l)["protocol"] == v3.VERSION]
        if prior:
            console.print("[bold red]The v3 holdout has already been used. Previous result:[/bold red]")
            console.print(json.dumps(prior[-1], indent=2))
            raise SystemExit(1)

    selection = shared.load_json(v3.SELECTION_PATH)
    if selection["status"] != "selected":
        raise SystemExit(f"Sweep rejected the strategy ({selection['reason']}); holdout not run.")
    variant = selection["selected"]

    console.print(f"[cyan]Protocol v3 holdout: {v3.label(variant)}, {v3.HOLDOUT_START:%Y-%m-%d} to {v3.HOLDOUT_END:%Y-%m-%d}[/cyan]")
    per_market = {}
    for symbol in v3.MARKETS:
        df = _fetch(symbol, v3.VALIDATION_START, v3.HOLDOUT_END)  # earlier data = indicator warm-up
        r = Backtester(v3.config_for(symbol, variant)).run(df, start=v3.HOLDOUT_START)
        buys = sum(1 for t in r["trade_log"] if t["action"] == "BUY")
        per_market[symbol] = {**_pick(r), "buys": buys, "open_at_end": r["open_position"] is not None}

    rets = [m["total_return_pct"] for m in per_market.values()]
    if all(m["buys"] == 0 for m in per_market.values()):
        outcome = "inconclusive"
    elif mean(rets) > 0 and sum(r > 0 for r in rets) >= v3.MIN_POSITIVE_MARKETS:
        outcome = "pass"
    else:
        outcome = "fail"

    record = {
        "protocol": v3.VERSION,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "label": v3.label(variant),
        "holdout": [v3.HOLDOUT_START, v3.HOLDOUT_END],
        "markets": per_market,
        "mean_return_pct": mean(rets),
        "outcome": outcome,
    }
    with open(shared.HOLDOUT_LOG_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    for s, m in per_market.items():
        console.print(
            f"  {s}: return {_pct(m['total_return_pct'])} vs buy & hold {_pct(m['buy_hold_pct'])}, "
            f"{m['buys']} entries, {m['total_trades']} closed, max drawdown {m['max_drawdown_pct']:.1f}%"
            + (", position open at end" if m["open_at_end"] else "")
        )
    color = {"pass": "green", "fail": "red", "inconclusive": "yellow"}[outcome]
    console.print(f"[bold {color}]Holdout {outcome.upper()}[/bold {color}] (mean return {mean(rets):+.2f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Research protocol v3")
    parser.add_argument("step", choices=["sweep", "holdout"])
    {"sweep": sweep, "holdout": holdout}[parser.parse_args().step]()
