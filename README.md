# algorhythm

A crypto algorithmic trading bot that uses a moving average crossover combined with RSI to
generate trading signals, executed against a simulated (paper) portfolio.

## Setup

```bash
git clone <this-repo>
cd algorhythm
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to set your exchange, symbol, and timeframe. API keys are optional — the bot only
fetches public OHLCV market data and trades on a simulated paper portfolio, so no exchange
account or credentials are required.

## Running

```bash
python main.py
```

On startup, the bot runs one trading cycle immediately, then repeats every 15 minutes. Each
cycle fetches the latest candles, computes indicators, checks for a signal, and (if triggered)
executes a simulated trade, printing indicator values, trades, and portfolio value to the
console.

## Strategy

The bot combines two signals on each completed candle:

- **Moving average crossover** — a short-period EMA (default 9) crossing above a long-period
  EMA (default 21) is a bullish "golden cross"; crossing below is a bearish "death cross".
  SMA values are also computed and logged for reference.
- **RSI (Relative Strength Index)** — used as a filter/override. An RSI above the overbought
  threshold (default 70) forces a SELL; an RSI below the oversold threshold (default 30) forces
  a BUY. Both override the crossover signal.

Signal rules:

- **BUY** — RSI is below the oversold threshold, OR a golden cross occurred with RSI below overbought.
- **SELL** — death cross occurred, or RSI is above the overbought threshold.
- **HOLD** — otherwise.

Position sizing risks a fixed percentage of the current balance per trade (default 2%), and
every open position carries a stop-loss (default 3% from entry) that is checked on every cycle.

## Execution model

The live bot and the backtester share the same `PaperTrader`, so results are directly comparable:

- Signals are evaluated only on **completed** candles; the still-forming candle is dropped.
  The live loop also skips a cycle if no new candle has closed since the last one.
- BUY/SELL fills at the candle close, adjusted against you by `SLIPPAGE_PCT` (default 0.05%).
- Stop-losses trigger when the candle's **low** touches the stop, and fill at the stop price
  (or at the open if price gapped through it), minus slippage.
- Every fill pays `FEE_PCT` (default 0.40%, roughly Kraken's entry-tier taker fee). Reported
  P&L is net of fees.

## Backtesting

```bash
python backtest.py --days 90
```

Backtest history comes from `HISTORY_EXCHANGE` (default `kucoin`), not the live exchange:
Kraken's public OHLC endpoint only returns its most recent 720 candles (~7.5 days at 15m).
The fetcher checks coverage and errors out rather than silently backtesting a shorter period.

## Disclaimer

This project runs in **paper trading mode by default** — it simulates trades against an
in-memory balance and never places real orders. It is intended for **educational purposes
only** and is not financial advice. Do not use this as the basis for live trading without
significant further testing and risk management.
