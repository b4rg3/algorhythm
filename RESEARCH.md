# Research protocol (v1)

This file fixes **how** strategies are evaluated *before* any results are computed, so that
we can't move the goalposts after seeing numbers. It was committed before the analyses it
describes were run; the git history is the audit trail.

The rules are encoded in `research/protocol.py`. Decisions produced by each step are
written to `research/` and committed.

## Data

- Market: DOGE/USDT, history from KuCoin (`HISTORY_EXCHANGE`), cross-checked against
  CoinGecko before use.
- Window: the 730 days ending **2026-11-11 00:00 UTC** (fixed, so reruns see identical data).
- Costs: 0.40% fee + 0.05% slippage per fill, i.e. **0.90% per round trip**.

## Splits (by time, never shuffled)

| Segment | Span | Used for |
|---|---|---|
| Train | first 70% of the pre-holdout data | exploring, ranking variants |
| Validation | remaining 30% of the pre-holdout data | choosing one variant |
| **Holdout** | final 90 days (2026-08-13 to 2026-11-11) | one final check, run once |

Indicators may warm up on earlier candles; trades only happen inside the segment.

**Disclosure:** before this protocol existed, the original 15m EMA 9/21 + RSI configuration
was backtested over windows that overlap the holdout (results were strongly negative).
No other configuration, and no other timeframe, has been evaluated on holdout data.
DOGE's raw price path over the past year (a ~60% decline with short rallies) has also been
viewed via CoinGecko. That is general market knowledge, not a strategy result, but it means
the holdout's market regime is not a surprise.

## Step 1: choose the timeframe from costs, not returns

Candidates: 15m, 30m, 1h, 2h, 4h, 1d.

For each, compute the **median ATR(14) as a % of price over the train segment only**.
ATR is the typical per-candle price range. This uses price volatility only; no strategy is run.

**Rule:** pick the *fastest* timeframe whose median ATR% is at least **2× the round-trip
cost (≥ 1.80%)**. A crossover trade spans several candles, so requiring each candle's
typical range to be twice the cost of a trade is a modest, conservative bar. The timeframe
is then fixed for the rest of v1.

## Step 2: a fixed grid of 18 variants on that timeframe

| Setting | Values |
|---|---|
| EMA short / long | 9/21, 12/26, 20/50 |
| Trend filter (EMA length, 0 = off) | 0, 100, 200 |
| RSI-oversold buy | on, off |

Everything else stays at defaults (RSI 14, 70/30, 2% risk, 3% stop).
No variants may be added after results are seen without starting protocol v2.

## Step 3: selection rule

1. Discard variants with a train return ≤ 0 (after costs).
2. From the rest, select the variant with the **highest validation return**.
3. If none survive step 1, or the selected variant's validation return is ≤ 0, the strategy
   is **rejected** and the holdout is not run.
4. Fragility flag: report how many of the selected variant's grid neighbours (same
   timeframe, one setting changed by one step) are also positive on validation. A selected
   variant with no positive neighbours is reported as fragile.

## Step 4: holdout, once

Run the selected variant on the holdout segment exactly once (`holdout.py` logs every run
to `research/holdout_log.jsonl` and refuses to run twice for the same protocol version).

**Pass:** positive return after costs on the holdout. The result is also compared with
buy-and-hold over the same span. A pass is evidence, not proof.

## Step 5: forward paper trading

A variant that passes is paper-traded live on new data, which no backtest can have
overfit. Any change to the strategy rules after the holdout has been seen starts
protocol v2 with a new, later holdout window.
