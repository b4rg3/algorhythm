"""F1 checker: fidelity replay, weekly rise/fall asymmetry, checkpoint and final verdicts.

    python forward_check.py

Safe to run at any time. Before 26 complete weeks it only reports interim numbers, which
decide nothing (RESEARCH.md, F1).
"""

import json
import os

import pandas as pd
from rich.console import Console

from backtest.runner import Backtester
from research import f1
from research.capture import capture, weekly_returns

console = Console()


def load_symbol(symbol: str, base_dir: str = f1.DATA_DIR):
    """Return (candles incl. warm-up, daily rows, recorded trades) for one coin."""
    folder = f1.symbol_dir(symbol, base_dir)
    warm = pd.read_csv(os.path.join(folder, "warmup.csv"), index_col=0, parse_dates=True)
    warm.index = pd.to_datetime(warm.index, utc=True)
    rows = pd.DataFrame([json.loads(l) for l in open(os.path.join(folder, "daily.jsonl")) if l.strip()])
    rows["ts"] = pd.to_datetime(rows["ts"], utc=True)
    rows = rows.set_index("ts").sort_index()
    candles = pd.concat([warm[["open", "high", "low", "close", "volume"]],
                         rows[["open", "high", "low", "close", "volume"]]])
    trades_path = os.path.join(folder, "trades.jsonl")
    trades = [json.loads(l) for l in open(trades_path) if l.strip()] if os.path.exists(trades_path) else []
    for t in trades:
        t["ts"] = pd.Timestamp(t["ts"])
    return candles, rows, trades


def fidelity(symbol: str, candles: pd.DataFrame, rows: pd.DataFrame, trades: list[dict],
             start: pd.Timestamp) -> dict:
    """Replay the backtester over the recorded candles and compare trade by trade."""
    replay = Backtester(f1.config_for(symbol)).run(candles, start=start)["trade_log"]
    missed_days = set(rows.index[rows["missed"]])

    def key(t):
        return (pd.Timestamp(t["ts"]), t["action"])

    recorded = {key(t): t for t in trades}
    expected = {key(t): t for t in replay}
    mismatches, explained = [], []
    for k in sorted(set(recorded) | set(expected)):
        r, e = recorded.get(k), expected.get(k)
        ok = r is not None and e is not None and abs(r["price"] / e["price"] - 1) <= f1.FIDELITY_PRICE_TOL
        if ok:
            continue
        near_missed = any(abs((k[0] - d).days) <= 1 for d in missed_days)
        (explained if near_missed else mismatches).append(
            {"ts": str(k[0].date()), "action": k[1], "recorded": r and r["price"], "replay": e and e["price"]}
        )
    return {"trades": len(trades), "replay_trades": len(replay), "mismatches": mismatches,
            "explained_by_missed_closes": explained}


def evaluate(base_dir: str = f1.DATA_DIR, registered_at: pd.Timestamp = f1.REGISTERED_AT) -> dict:
    start = f1.start_candle(registered_at)
    per_symbol, weekly_all = {}, {}
    for symbol in f1.SYMBOLS:
        candles, rows, trades = load_symbol(symbol, base_dir)
        ref_ts = candles.index[candles.index < start][-1]
        equity = pd.concat([pd.Series([1000.0], index=[ref_ts]), rows["equity"]])
        close = candles["close"][candles.index >= ref_ts]
        weekly = weekly_returns(equity, close)
        weekly_all[symbol] = weekly
        per_symbol[symbol] = {
            "days": len(rows),
            "missed": int(rows["missed"].sum()),
            "fidelity": fidelity(symbol, candles, rows, trades, start),
            "equity": float(rows["equity"].iloc[-1]),
            "buy_hold_pct": float(rows["close"].iloc[-1] / candles["close"].loc[ref_ts] - 1) * 100,
        }

    complete = min(len(w) for w in weekly_all.values())
    result = {"start": start, "complete_weeks": complete, "symbols": per_symbol}

    def stage(weeks: int) -> dict:
        windows = {s: w.iloc[:weeks] for s, w in weekly_all.items()}
        pooled = capture(pd.concat(windows.values()))
        each = {s: capture(w) for s, w in windows.items()}
        return {"pooled": pooled, "each": each}

    fidelity_ok = all(not p["fidelity"]["mismatches"] for p in per_symbol.values())
    result["fidelity_ok"] = fidelity_ok
    result["interim"] = stage(complete) if complete else None

    if complete >= f1.CHECKPOINT_WEEKS:
        cp = stage(f1.CHECKPOINT_WEEKS)
        days_cp = f1.CHECKPOINT_WEEKS * 7
        too_many_missed = any(
            load_symbol(s, base_dir)[1].iloc[:days_cp]["missed"].sum() > f1.MAX_MISSED["checkpoint"]
            for s in f1.SYMBOLS
        )
        if not fidelity_ok:
            verdict = "fidelity failure (bug): fix, restart the clock"
        elif too_many_missed:
            verdict = "inconclusive (too many missed closes)"
        elif cp["pooled"].gap < f1.CONSISTENCY_FLOOR_PP:
            verdict = "CHECKPOINT FAILURE: gap below the historical 10th percentile"
        else:
            verdict = "checkpoint passed (within the normal range; decides nothing about the edge)"
        result["checkpoint"] = {**cp, "verdict": verdict}

    if complete >= f1.FINAL_WEEKS:
        fin = stage(f1.FINAL_WEEKS)
        no_trades = all(p["fidelity"]["trades"] == 0 for p in per_symbol.values())
        too_many_missed = any(p["missed"] > f1.MAX_MISSED["final"] for p in per_symbol.values())
        coins_ok = sum(
            1 for c in fin["each"].values()
            if c.gap > 0 and c.up_weeks >= f1.MIN_WEEKS_EACH_WAY and c.down_weeks >= f1.MIN_WEEKS_EACH_WAY
        )
        if not fidelity_ok:
            verdict = "fidelity failure (bug)"
        elif no_trades or too_many_missed:
            verdict = "INCONCLUSIVE"
        elif fin["pooled"].gap > 0 and coins_ok >= 2:
            verdict = "PASS"
        else:
            verdict = "FAIL"
        result["final"] = {**fin, "verdict": verdict}
    return result


def _fmt(c) -> str:
    return (f"kept {c.rises_kept_pct:.0f}% of rises, took {c.falls_taken_pct:.0f}% of falls, "
            f"gap {c.gap:+.0f} pp ({c.up_weeks} up / {c.down_weeks} down weeks)")


def main() -> None:
    try:
        r = evaluate()
    except FileNotFoundError:
        console.print("[yellow]F1 has no recorded candles yet.[/yellow]")
        return
    console.print(f"[cyan]F1 from {r['start']:%Y-%m-%d}: {r['complete_weeks']} complete weeks[/cyan]")
    for s, p in r["symbols"].items():
        fid = p["fidelity"]
        console.print(
            f"  {s}: {p['days']} days, value {p['equity']:.2f} USDT (buy & hold {p['buy_hold_pct']:+.1f}%), "
            f"{fid['trades']} trades (replay {fid['replay_trades']}), mismatches {len(fid['mismatches'])}, "
            f"missed closes {p['missed']}"
        )
        for m in fid["mismatches"]:
            console.print(f"    [bold red]mismatch[/bold red] {m}")
    console.print(f"Fidelity: {'[green]OK[/green]' if r['fidelity_ok'] else '[bold red]FAILED[/bold red]'}")
    if r["interim"]:
        console.print(f"Interim (decides nothing): pooled {_fmt(r['interim']['pooled'])}")
    for stage in ("checkpoint", "final"):
        if stage in r:
            console.print(f"[bold]{stage.title()}[/bold]: pooled {_fmt(r[stage]['pooled'])}")
            for s, c in r[stage]["each"].items():
                console.print(f"    {s}: {_fmt(c)}")
            console.print(f"[bold]{stage.title()} verdict: {r[stage]['verdict']}[/bold]")


if __name__ == "__main__":
    main()
