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

- **Moving average crossover** — a short-period SMA (default 9) crossing above a long-period
  SMA (default 21) is a bullish "golden cross"; crossing below is a bearish "death cross".
- **RSI (Relative Strength Index)** — used as a filter/override. An RSI above the overbought
  threshold (default 70) forces a SELL regardless of the crossover, guarding against buying
  into an already-overextended move.

Signal rules:

- **BUY** — golden cross occurred and RSI is below the overbought threshold.
- **SELL** — death cross occurred, or RSI is above the overbought threshold.
- **HOLD** — otherwise.

Position sizing risks a fixed percentage of the current balance per trade (default 2%), and
every open position carries a stop-loss (default 3% from entry) that is checked on every cycle.

## Disclaimer

This project runs in **paper trading mode by default** — it simulates trades against an
in-memory balance and never places real orders. It is intended for **educational purposes
only** and is not financial advice. Do not use this as the basis for live trading without
significant further testing and risk management.
