"""Protocol step 4: evaluate the selected variant on the holdout segment, ONCE.

Refuses to run if step 3 rejected the strategy, or if the holdout has already been used
for this protocol version (every run is logged to research/holdout_log.jsonl).
"""

import json
import os
from datetime import datetime, timezone

from rich.console import Console

from backtest.runner import Backtester
from data.coingecko import cross_check
from data.fetcher import DataFetcher
from research import protocol as P


def _previous_runs() -> list[dict]:
    if not os.path.exists(P.HOLDOUT_LOG_PATH):
        return []
    with open(P.HOLDOUT_LOG_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    console = Console()
    prior = [r for r in _previous_runs() if r["protocol"] == P.VERSION]
    if prior:
        console.print(f"[bold red]The {P.VERSION} holdout has already been used. Previous result:[/bold red]")
        console.print(json.dumps(prior[-1], indent=2))
        raise SystemExit(1)

    selection = P.load_json(P.SELECTION_PATH)
    if selection["status"] != "selected":
        raise SystemExit(f"Step 3 rejected the strategy ({selection['reason']}); holdout not run.")

    sp = P.splits()
    tf = selection["timeframe"]
    variant = selection["selected"]
    cfg = P.base_config(timeframe=tf, **variant)

    # Load from the validation start so indicators are warm when the holdout begins.
    df = DataFetcher(cfg, exchange_id=cfg.history_exchange).fetch_history(
        days=(sp.end - sp.validation_start).days, end=sp.end
    )
    try:
        check = cross_check(df[df.index >= sp.holdout_start], cfg.coingecko_id, tf)
        console.print(f"CoinGecko cross-check (holdout) {check.summary()}")
        if not check.ok:
            raise SystemExit("Holdout data doesn't track CoinGecko; not consuming the holdout.")
    except RuntimeError as exc:
        console.print(f"[yellow]CoinGecko cross-check unavailable: {exc}[/yellow]")

    r = Backtester(cfg).run(df, start=sp.holdout_start)
    passed = r["total_return_pct"] > 0

    record = {
        "protocol": P.VERSION,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "symbol": cfg.symbol,
        "timeframe": tf,
        "variant": variant,
        "label": P.variant_label(variant),
        "holdout": [sp.holdout_start, sp.end],
        "total_return_pct": r["total_return_pct"],
        "buy_hold_pct": r["buy_hold_pct"],
        "total_trades": r["total_trades"],
        "profit_factor": r["profit_factor"] if r["profit_factor"] != float("inf") else "inf",
        "max_drawdown_pct": r["max_drawdown_pct"],
        "total_fees": r["total_fees"],
        "passed": passed,
    }
    with open(P.HOLDOUT_LOG_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    color = "green" if passed else "red"
    console.print(
        f"[bold {color}]Holdout {'PASSED' if passed else 'FAILED'}[/bold {color}]: "
        f"{P.variant_label(variant)} on {tf}, {sp.holdout_start:%Y-%m-%d} to {sp.end:%Y-%m-%d}\n"
        f"  return {r['total_return_pct']:+.2f}% vs buy & hold {r['buy_hold_pct']:+.2f}%, "
        f"{r['total_trades']} trades, max drawdown {r['max_drawdown_pct']:.1f}%, "
        f"fees {r['total_fees']:.2f} USDT"
    )


if __name__ == "__main__":
    main()
