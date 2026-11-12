"""F1 forward paper test runner (RESEARCH.md).

    python f1.py run      # process any newly closed daily candles (safe to run hourly)
    python f1.py status   # show the paper portfolios

Per coin, everything is recorded under logs/f1/<SYMBOL>/:
  warmup.csv      the candles before the start (for indicator warm-up and the fidelity replay)
  daily.jsonl     one row per daily candle in the test: OHLC, equity, signal, action, delays
  trades.jsonl    each paper trade, with Kraken's live spread and depth at the time
  portfolio.json  the paper portfolio state
"""

import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd
from rich.console import Console

from data.fetcher import DataFetcher
from execution.paper_trader import PaperTrader
from research import f1
from risk.manager import RiskManager
from strategy.factory import make_strategy

console = Console()


def _append(path: str, row: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def _book_stats(exchange, symbol: str, side: str, notional: float) -> dict:
    """Spread and the cost of filling `notional` USDT against Kraken's live book."""
    try:
        ob = exchange.fetch_order_book(symbol, limit=500)
        bid, ask = ob["bids"][0][0], ob["asks"][0][0]
        mid = (bid + ask) / 2
        levels = ob["asks"] if side == "buy" else ob["bids"]
        left, cost, qty = notional, 0.0, 0.0
        for level in levels:
            price, size = level[0], level[1]
            take = min(size, left / price)
            cost, qty, left = cost + take * price, qty + take, left - take * price
            if left <= 1e-9:
                break
        slip = None
        if qty and left <= 1e-6:
            avg = cost / qty
            slip = (avg / mid - 1) * 100 if side == "buy" else (1 - avg / mid) * 100
        return {"bid": bid, "ask": ask, "spread_pct": (ask - bid) / mid * 100, "est_slippage_pct": slip}
    except Exception as exc:  # book stats are informational; never block the test on them
        return {"error": str(exc)}


def run_symbol(symbol: str, base_dir: str = f1.DATA_DIR, now: pd.Timestamp | None = None,
               fetcher_factory=DataFetcher, registered_at: pd.Timestamp = f1.REGISTERED_AT) -> str:
    """Process newly closed candles for one coin. Returns a one-line summary."""
    now = now or pd.Timestamp.now(tz="UTC")
    cfg = f1.config_for(symbol)
    start = f1.start_candle(registered_at)
    folder = f1.symbol_dir(symbol, base_dir)
    os.makedirs(folder, exist_ok=True)

    fetcher = fetcher_factory(cfg)
    df = fetcher.fetch_candles(limit=f1.FETCH_LIMIT)  # completed candles only
    df = df[df.index + f1.CANDLE <= now]
    if df.empty or df.index[-1] < start:
        return f"{symbol}: waiting for the first F1 candle ({start:%Y-%m-%d}, closes {start + f1.CANDLE:%Y-%m-%d %H:%M} UTC)"

    warmup_path = os.path.join(folder, "warmup.csv")
    if not os.path.exists(warmup_path):
        warm = df[df.index < start]
        if len(warm) < cfg.trend_sma_period + 1:
            raise RuntimeError(f"{symbol}: only {len(warm)} warm-up candles before the start")
        warm.to_csv(warmup_path)

    trader = PaperTrader(cfg, state_path=os.path.join(folder, "portfolio.json"))
    last = pd.Timestamp(trader.last_candle_ts) if trader.last_candle_ts else None
    pending = df[(df.index >= start) & ((df.index > last) if last is not None else True)]
    if pending.empty:
        return f"{symbol}: up to date (last candle {last:%Y-%m-%d})"

    strategy = make_strategy(cfg)
    rm = RiskManager(cfg)
    daily_path = os.path.join(folder, "daily.jsonl")
    trades_path = os.path.join(folder, "trades.jsonl")
    processed_at = now.isoformat()
    summary = []

    # Every pending candle except the newest closed while the bot wasn't running: missed.
    for ts, row in pending.iloc[:-1].iterrows():
        _append(daily_path, {
            "ts": ts, "open": row.open, "high": row.high, "low": row.low, "close": row.close,
            "volume": row.volume, "equity": trader.portfolio_value(row.close),
            "in_market": trader.position is not None, "signal": None, "action": None,
            "missed": True, "processed_at": processed_at,
        })
        summary.append(f"missed {ts:%Y-%m-%d}")

    ts = pending.index[-1]
    candle = pending.iloc[-1]
    prepared = strategy.prepare(df[df.index <= ts])
    signal = strategy.signal(prepared)
    trade = trader.execute(signal, candle, rm, candle_ts=ts)

    if trade is not None:
        side = "buy" if trade["action"] == "BUY" else "sell"
        trade_row = {"ts": ts, **trade, "processed_at": processed_at,
                     "book": _book_stats(fetcher.exchange, symbol, side, trade["quantity"] * trade["price"])}
        _append(trades_path, trade_row)
        summary.append(f"{trade['action']} {trade['quantity']:.6f} @ {trade['price']:.6g}")

    _append(daily_path, {
        "ts": ts, "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close,
        "volume": candle.volume, "equity": trader.portfolio_value(candle.close),
        "in_market": trader.position is not None, "signal": signal,
        "action": trade["action"] if trade else None, "missed": False,
        "processed_at": processed_at,
        "delay_hours": round((now - (ts + f1.CANDLE)).total_seconds() / 3600, 2),
    })
    value = trader.portfolio_value(candle.close)
    return f"{symbol}: {ts:%Y-%m-%d} close {candle.close:.6g}, signal {signal}, value {value:.2f}" + (
        f" ({'; '.join(summary)})" if summary else ""
    )


def run() -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for symbol in f1.SYMBOLS:
        try:
            console.print(f"[dim]{stamp}[/dim] {run_symbol(symbol)}")
        except Exception as exc:
            console.print(f"[dim]{stamp}[/dim] [bold red]{symbol}: ERROR {exc}[/bold red]")


def status() -> None:
    start = f1.start_candle()
    console.print(f"[cyan]F1 forward test, first candle {start:%Y-%m-%d} (closes {start + f1.CANDLE:%Y-%m-%d %H:%M} UTC)[/cyan]")
    for symbol in f1.SYMBOLS:
        folder = f1.symbol_dir(symbol)
        path = os.path.join(folder, "daily.jsonl")
        if not os.path.exists(path):
            console.print(f"  {symbol}: no candles processed yet")
            continue
        rows = [json.loads(l) for l in open(path) if l.strip()]
        last = rows[-1]
        missed = sum(r["missed"] for r in rows)
        console.print(
            f"  {symbol}: {len(rows)} days, last {last['ts'][:10]}, value {last['equity']:.2f} USDT, "
            f"{'holding' if last['in_market'] else 'cash'}, missed closes {missed}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 forward paper test")
    parser.add_argument("command", choices=["run", "status"])
    {"run": run, "status": status}[parser.parse_args().command]()
