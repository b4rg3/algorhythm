# Research protocols

This file fixes **how** strategies are evaluated *before* any results are computed, so that
we can't move the goalposts after seeing numbers. It was committed before the analyses it
describes were run; the git history is the audit trail.

The rules are encoded in `research/protocol.py`. Decisions produced by each step are
written to `research/<version>/` and committed. Every holdout run, for any version, is
logged to `research/holdout_log.jsonl`. Select a version with `PROTOCOL=v1` (default: latest).

## Versions

| Version | Market | Status |
|---|---|---|
| v1 | DOGE/USDT | **Rejected** at step 3: all 18 variants lost money on train (DOGE −72%). Holdout unused. |
| v2 | ETH/USDT | **Rejected** at step 3: 2 of 18 variants were positive on train (+1.9%, +1.1%; ETH −28.7%), both lost 10.9% on validation. Timeframe 4h. Holdout unused. |
| v3 | BTC + ETH + DOGE, daily | **Failed holdout.** Sweep: all 8 variants positive on train and validation; SMA100 band 2% selected (validation mean +68.8%). Holdout mean −0.11% (BTC +7.0%, ETH +6.8%, DOGE −14.1%; 4 trades in total), below buy & hold on all three. |

The rules below were written for v1 and apply unchanged to every version unless a version's
section says otherwise.

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
overfit. Any change to the strategy rules after the holdout has been seen starts a new
protocol version, which needs a holdout that no earlier version has evaluated.

---

## v2: ETH/USDT

**Only change from v1: the market** (ETH/USDT, cross-checked against CoinGecko `ethereum`).
Strategy, variant grid, data window and splits, timeframe rule, selection rule and pass
criterion are all identical to v1. In particular, the pass bar is still a positive return
after costs on the holdout. It was not relaxed after seeing v1's results.

Disclosures:
- **Multiple testing:** ETH was chosen *after* the strategy failed on DOGE. v2 is a second
  attempt with the same strategy, so a v2 pass is somewhat weaker evidence than a first-try
  pass would be. Any further markets will add to this count.
- No backtest of any kind has been run on ETH data before this protocol was committed.
  ETH's current spot price (~$2,076 on 2026-11-11) was seen via CoinGecko; its price history
  over the window has not been reviewed in this project.
- The live bot is not affected by this protocol; its SYMBOL stays as configured in `.env`.

---

## v3: daily trend-following

v1 and v2 tested the same 2h/4h crossover strategy and rejected it on both markets. v3 tests a
**different strategy**, chosen for structural reasons, not because of any result on v3's own
rules:

- **Daily candles** make costs small relative to typical moves (daily ATR was 7.8% for DOGE
  and 5.7% for ETH against a 0.90% round trip).
- **Few trades.** Slow trend rules typically make a handful of round trips per year.
- **Built to sit out declines.** In v1/v2 the only consistently helpful component was the
  long-term trend filter, which cut losses by keeping the bot in cash.

### Strategy

Long-only, evaluated once per day on the completed daily candle:

- **Enter** (go fully long) when `close > SMA(N) × (1 + b)`.
- **Exit** (go fully to cash) when `close < SMA(N) × (1 − b)`.
- Otherwise keep the current state. The band `b` reduces whipsaw around the average.

Execution and sizing:

- Fills at the daily close with the same costs as v1/v2: 0.40% fee + 0.05% slippage per fill.
- **Position size: 100% of available balance** (net of fees). The v1/v2 rule (risk 2% with
  a 3% stop) doesn't fit daily trend-following: a 3% stop sits well inside a single day's
  normal range.
- **No fixed stop-loss.** The trend exit is the stop. This is a deliberate trade-off: losses
  between daily closes are not capped.

### Markets: one parameter set across three markets

BTC/USDT, ETH/USDT and DOGE/USDT, daily candles from **Gate**, cross-checked against
CoinGecko where its public API reaches (the last 365 days). Gate is used instead of KuCoin
because KuCoin's DOGE/USDT daily history only starts in early 2021. Gate covers all three
markets from 2019-05-01 with no missing days. That was checked before this protocol was
committed, by looking only at candle dates; no strategy was run.

**The same variant must be used on all three markets.** Choosing per market would triple the
chances of fitting noise. Requiring one rule to work broadly is a stronger test.

### Data and splits

Daily candles need far more history than 730 days: a 200-day average uses most of a year
just to warm up. So v3 uses a longer window. The holdout is the same untouched span as v1/v2.

| Segment | Span | Notes |
|---|---|---|
| Train | 2020-01-01 to 2023-12-31 | 2020–21 bull, 2022 bear, 2023 recovery |
| Validation | 2024-01-01 to 2026-08-13 | Overlaps v1/v2 train/validation (see disclosures) |
| **Holdout** | 2026-08-13 to 2026-11-11 | No strategy has been evaluated here on any market |

Indicators warm up on data before each segment.

### Variant grid (8 variants, fixed)

| Setting | Values |
|---|---|
| SMA length N (days) | 50, 100, 150, 200 |
| Band b | 0%, 2% |

No other settings are varied.

### Selection rule

1. A variant **survives** if, on the train segment, it has a positive return after costs on
   at least 2 of 3 markets **and** at least 5 closed trades on each market. The trade minimum
   exists because v2's only survivors had 6–8 trades.
2. Among survivors, select the variant with the **highest average validation return across
   the three markets**.
3. **Reject** if nothing survives, or if the selected variant's average validation return
   is ≤ 0.
4. Report the fragility check as in v1: whether neighbouring N values with the same band are
   also positive on validation.

### Holdout (run once)

- **Pass:** average holdout return across the three markets > 0 after costs, **and**
  positive on at least 2 of 3.
- **Inconclusive:** if the selected variant takes no position on any market during the
  holdout (possible, since it is a slow strategy in a falling market), the result is
  recorded as inconclusive, not as a pass or a fail.
- Also reported: buy-and-hold and max drawdown per market.

**Power warning:** 90 daily candles will contain very few trades (likely 0–2 per market),
so the holdout can catch a clear failure but can't confirm an edge. Forward paper trading
(step 5) is the primary test for v3. A pass sends the variant to paper trading; it is not
a verdict.

### Disclosures

- **Third attempt.** v1 and v2 failed. v3 is a different strategy, but the idea was
  partly informed by v1/v2's results (the trend filter helped). Count so far: 18 + 18 + 8
  variants.
- **Validation overlap.** The validation segment (2024-01 to 2026-08) overlaps data on which
  v1/v2 evaluated a different strategy, and DOGE's price path over the past year has been
  viewed. The market regime of the later validation period (a broad decline) is known.
- **New window.** The data window differs from v1/v2. That is because daily candles need
  more history, and it was fixed before any v3 result was computed.
- BTC has not been backtested in this project.

### Implementation (written after this protocol was committed)

- A trend strategy class (SMA + band, stateful enter/exit) alongside the existing MA/RSI one.
- A full-allocation sizing mode and an option to disable the fixed stop in `PaperTrader`.
- Multi-market support in the protocol scripts (sweep and holdout across three symbols).
- The live bot will be able to run v3 (Kraken serves 720 daily candles, enough for SMA 200),
  but only after a pass.
