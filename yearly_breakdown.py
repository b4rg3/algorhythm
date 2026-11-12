"""Year-by-year breakdown of v3's rule vs buy & hold, over train + validation only.

Descriptive analysis: it makes no selection and never loads holdout data (it stops at
v3's holdout start). Each market is run continuously from 2020-01-01, so positions carry
across year boundaries, then returns are split by calendar year.

    python yearly_breakdown.py
"""

from statistics import mean

import pandas as pd
from rich.console import Console
from rich.table import Table

from backtest.runner import Backtester
from data.fetcher import DataFetcher
from research import v3

SELECTED = {"sma": 100, "band": 0.02}


def _pct(v: float) -> str:
    color = "green" if v > 0 else "red"
    return f"[{color}]{v:+.0f}%[/{color}]"


def _max_dd(series: pd.Series) -> float:
    return float(((series.cummax() - series) / series.cummax()).max() * 100)


def yearly(result: dict) -> pd.DataFrame:
    eq, close, inm = result["equity_curve"], result["close"], result["in_market"]
    start_eq = pd.concat([pd.Series([1000.0], index=[close.index[0]]), eq])
    rows = []
    for year in sorted(set(eq.index.year)):
        e = start_eq[start_eq.index.year <= year]
        e = e[e.index >= (e[e.index.year < year].index.max() if (e.index.year < year).any() else e.index[0])]
        c = close[close.index.year <= year]
        c = c[c.index >= (c[c.index.year < year].index.max() if (c.index.year < year).any() else c.index[0])]
        sells = [t for t in result["trade_log"] if "pnl" in t and t["ts"].year == year]
        rows.append({
            "year": year,
            "strategy": (e.iloc[-1] / e.iloc[0] - 1) * 100,
            "buy_hold": (c.iloc[-1] / c.iloc[0] - 1) * 100,
            "strategy_dd": _max_dd(e),
            "buy_hold_dd": _max_dd(c),
            "in_market": inm[inm.index.year == year].mean() * 100,
            "trades": len(sells),
        })
    return pd.DataFrame(rows).set_index("year")


def main() -> None:
    console = Console()
    console.print(
        f"[cyan]v3 rule ({v3.label(SELECTED)}) vs buy & hold by calendar year, "
        f"{v3.TRAIN_START:%Y-%m-%d} to {v3.HOLDOUT_START:%Y-%m-%d} (holdout excluded). "
        f"Costs: 0.40% fee + 0.05% slippage per fill.[/cyan]"
    )

    per_market: dict[str, pd.DataFrame] = {}
    all_variants: dict[str, list[pd.DataFrame]] = {}
    for symbol in v3.MARKETS:
        cfg0 = v3.config_for(symbol, SELECTED)
        df = DataFetcher(cfg0, exchange_id=v3.HISTORY_EXCHANGE).fetch_history(
            days=(v3.HOLDOUT_START - v3.DATA_START).days, end=v3.HOLDOUT_START
        )
        per_market[symbol] = yearly(Backtester(cfg0).run(df, start=v3.TRAIN_START))
        all_variants[symbol] = [
            yearly(Backtester(v3.config_for(symbol, v)).run(df, start=v3.TRAIN_START)) for v in v3.grid()
        ]

    for symbol, yt in per_market.items():
        t = Table(title=f"{symbol}: {v3.label(SELECTED)}", header_style="bold")
        for col in ["Year", "Strategy", "Buy & hold", "Difference", "Strat max DD", "B&H max DD", "In market", "Closed trades", "All 8 variants: diff"]:
            t.add_column(col, justify="right")
        for year, r in yt.iterrows():
            all8 = mean(v.loc[year, "strategy"] - v.loc[year, "buy_hold"] for v in all_variants[symbol])
            t.add_row(
                str(year) + ("*" if year == 2026 else ""),
                _pct(r.strategy), _pct(r.buy_hold), _pct(r.strategy - r.buy_hold),
                f"{r.strategy_dd:.0f}%", f"{r.buy_hold_dd:.0f}%", f"{r.in_market:.0f}%",
                str(int(r.trades)), _pct(all8),
            )
        console.print(t)

    summary = Table(title="Average across BTC, ETH, DOGE", header_style="bold")
    for col in ["Year", "Strategy", "Buy & hold", "Difference", "Strat max DD", "B&H max DD", "In market"]:
        summary.add_column(col, justify="right")
    years = per_market[next(iter(per_market))].index
    for year in years:
        avg = {k: mean(per_market[s].loc[year, k] for s in per_market) for k in ("strategy", "buy_hold", "strategy_dd", "buy_hold_dd", "in_market")}
        summary.add_row(
            str(year) + ("*" if year == 2026 else ""),
            _pct(avg["strategy"]), _pct(avg["buy_hold"]), _pct(avg["strategy"] - avg["buy_hold"]),
            f"{avg['strategy_dd']:.0f}%", f"{avg['buy_hold_dd']:.0f}%", f"{avg['in_market']:.0f}%",
        )
    console.print(summary)
    console.print("[dim]* 2026 runs Jan 1 to Aug 12 (holdout excluded). Max DD = largest peak-to-trough fall within the year.[/dim]")


if __name__ == "__main__":
    main()
