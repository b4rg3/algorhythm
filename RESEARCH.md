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
| F1 | v3 rule, forward on Kraken | **Registered 2026-11-12.** Forward paper test of the unchanged v3 rule, judged on rise/fall asymmetry; six-month checkpoint, two-year verdict. |
| v4 | v3 rule + funding filter | Draft: funding-rate filter; forward-only holdout. |

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

---

## F1: forward paper test of v3

v3 failed its holdout narrowly (mean −0.11% on 4 trades). The holdout was too short to
judge a daily strategy either way. F1 tests the **unchanged** v3 rule on data that doesn't
exist yet, which nothing can have been fitted to. F1 is not a re-scoring of v3: v3's
recorded result stays "failed holdout".

### What runs

- **Rule:** v3's selected variant, frozen: SMA 100, band 2%, daily candles, long or cash,
  100% allocation, no fixed stop. No parameter may change during F1.
- **Markets:** BTC/USDT, ETH/USDT, DOGE/USDT, each with its own 1,000 USDT paper portfolio.
- **Data and venue:** live daily candles from **Kraken**, the venue we'd actually trade on.
- **Costs:** the same model as v3 (0.40% fee + 0.05% slippage per fill), so results compare
  with the backtests. The bot also logs Kraken's live spread and order-book depth at every
  fill. Those measurements feed future cost models, not F1's verdict.
- **Starting state:** flat. On the first daily close, any market already more than 2% above
  its SMA 100 is bought, just as the backtests did at each segment start.

### What F1 tests: the claim, not the profit

A year-by-year and month-by-month breakdown of v3's rule (train + validation only,
`yearly_breakdown.py`) showed that whether it beats or makes money depends mostly on the
market's direction. It trails buy & hold in every rising year and beats it in every falling
year. Its one regime-independent property is **asymmetry**: it keeps a larger share of the
market's rises than it takes of the market's falls.

F1 therefore tests that asymmetry, not raw return. A return-based verdict would mostly measure
whether crypto went up or down during the test.

**Measurement**, on calendar weeks (Monday to Sunday, UTC) that fall fully inside the test:

- For each coin and week: the strategy's return `s` (paper portfolio value, after costs) and
  the coin's return `b` (Kraken close to close).
- **Share of rises kept** = sum of `s` over weeks with `b > 0`, divided by the sum of `b`
  over those weeks.
- **Share of falls taken** = sum of `s` over weeks with `b < 0`, divided by the sum of `b`
  over those weeks.
- **Gap** = share of rises kept − share of falls taken, in percentage points. "Pooled" means
  computed over all coin-weeks of the three coins together.

**Historical reference** (Gate data, 2020 to 2026-08-13, measured before this section was
committed):

| | Share of rises kept | Share of falls taken | Gap |
|---|---|---|---|
| Pooled, 2020 to Aug 2026 | 67% | 55% | +12 pp |
| Pooled, 2024 to Aug 2026 | 58% | 45% | +13 pp |

Over rolling windows since 2020, the pooled gap was positive in:

| Window length | Gap > 0 | Median gap | 10th to 90th percentile |
|---|---|---|---|
| 26 weeks | 41% of windows | −4 pp | −22 to +14 pp |
| 52 weeks | 59% | +4 pp | −11 to +13 pp |
| 104 weeks | 73% | +9 pp | −5 to +20 pp |

**The edge is real over the full history but weak and slow to appear.** Over six months, the
rule behaving exactly as it always has shows its asymmetry less than half the time. So six
months can catch bugs and clear breakdowns, but it can't confirm the edge. F1 has a
six-month checkpoint and a two-year final verdict.

### Dates

- **Start:** the first daily close after this section is committed and the bot is running.
  The exact start candle is logged.
- **Checkpoint:** 26 complete weeks after the start.
- **Final verdict:** 104 complete weeks after the start (about two years).
- **No early stopping for performance,** good or bad. Implementation bugs are the only
  reason to stop. A bug fix restarts the clock and is recorded here.

### Six-month checkpoint (decided now)

1. **Fidelity (must pass):** replay the backtester over Kraken's candles for the same period.
   Every forward-test trade must match the replay: same day, same action, fill within 0.1%
   of the replay price. Any mismatch means a bug, the clock restarts after the fix, and no
   performance verdict is drawn.
2. **Consistency:** the pooled 26-week gap must be **at least −22 pp**, the historical 10th
   percentile. Worse than that is outside the range where the rule normally lands
   (historically about 1 window in 10), and counts as a **checkpoint failure**: F1 stops, and
   the rule is treated as broken or no longer working.
3. **Not judged at six months:** a positive or negative gap within the normal range. That
   outcome is expected roughly half the time either way, so it is reported but decides nothing.

### Two-year final verdict (decided now)

- **Pass:** pooled 104-week gap > 0, **and** gap > 0 on at least 2 of 3 coins, **and** each of
  those coins has at least 10 rising and 10 falling weeks.
- **Fail:** otherwise.
- **Inconclusive:** no trades at all on any coin, or the missed-close limit below is exceeded.
- **Power note:** even a rule that truly has its historical edge passed the pooled-gap part
  in only about 73% of historical two-year windows. A fail is meaningful evidence against the
  rule, but not proof. A pass is the strongest evidence this project can produce without
  real money.
- **Reported, not judged:** return versus buy & hold, max drawdown, and time in the market,
  per coin and pooled.

### Missed closes

If the bot is offline at a daily close, it acts on the next run, and the delay and price
difference are logged. More than 5 missed closes per coin in the first 26 weeks, or 20 over
the full 104 weeks, makes that stage inconclusive. Beyond that, the test measures the
computer's uptime rather than the strategy.

### What F1 means for real money

- F1 does not by itself approve real money. Whether to trade a small real amount after a clean
  six-month checkpoint is the user's decision, made knowing the edge is unconfirmed until the
  two-year verdict.
- A checkpoint failure or a fidelity failure rules real money out.

### Implementation needed (after commit)

- Multi-market support in the live bot: one paper portfolio, state file and trade log per
  symbol.
- Spread and depth logging at each fill.
- `forward_check.py` to run the fidelity replay and compute the weekly shares of rises kept
  and falls taken, the checkpoint and the final verdict. It is tested against the historical
  numbers above before F1 starts.
- An always-on machine, or a scheduled task shortly after 00:00 UTC each day.

---

## v4: funding-rate filter on v3 (DRAFT, under review, not yet committed or run)

### Hypothesis

Perpetual-futures **funding rates** measure how crowded leveraged long positions are.
When funding is extremely positive, the market is over-leveraged long and prone to sharp
"long squeeze" drops. A trend-following entry made into crowded leverage should, on
average, do worse. A filter that avoids those entries might keep v3's trend gains while
cutting some of its losses.

The idea came from external research the user supplied, not from v3's holdout trades. But
v3's holdout trades are known (one DOGE entry lost 14.1%), so v4 **cannot** use that
holdout. See "Holdout" below.

### Strategy

The base is **v3's selected rule, frozen** (SMA 100, band 2%, daily, 100% allocation, no
fixed stop), plus a funding filter:

- `F` = the trailing 7-day average of the perpetual funding rate (per 8-hour period), using
  only funding events settled by the daily close.
- **Extreme** = `F ≥ T`, where T is the threshold. Binance's neutral funding level is 0.01%
  per 8h.
- **Filter action** (one of two modes):
  - **block:** no new entry while funding is extreme. Exits work as in v3.
  - **block + exit:** as above, and also exit a long when funding turns extreme.

### Variant grid (4 variants, fixed)

| Setting | Values |
|---|---|
| Threshold T (per 8h, 7-day average) | 0.03% (3× neutral), 0.05% (5× neutral) |
| Action | block, block + exit |

The baseline (v3 without the filter) is run alongside on every segment for comparison.

### Data

- **Prices:** Gate daily candles for BTC/USDT, ETH/USDT, DOGE/USDT, the same source as v3.
- **Funding:** Binance USDⓈ-M perpetual funding history (BTCUSDT, ETHUSDT, DOGEUSDT) from
  Binance's public bulk files (data.binance.vision), which are reachable from this network.
  Binance is the largest perpetuals venue, so its funding is the most representative.
- **Availability** (checked before writing this draft; dates only, no strategy run): BTC
  and ETH funding files start 2020-01; DOGE starts 2020-07.
- **Live source for later forward testing:** OKX's public API (Binance's API is blocked
  here). Over the 77 overlapping days checked, OKX's 7-day average funding differed from
  Binance's by about 0.001% per 8h (correlation 0.88 BTC, 0.83 ETH, 0.65 DOGE). That's an
  order of magnitude below the thresholds, so it wouldn't change which days are extreme.
- **Excluded:** open interest (Binance history only from about Dec 2021), liquidations (paid
  data), order-book signals (time scales far shorter than a daily strategy).

### Splits

| Segment | Span | Notes |
|---|---|---|
| Train | 2020-08-01 to 2023-12-31 | Starts once DOGE funding has a full 7 days |
| Validation | 2024-01-01 to 2026-08-13 | Same as v3 |
| Holdout | **None from history.** v4's holdout is forward data (see below). | |

### Selection rule

Metrics are averaged across the three markets.

1. A variant **survives** if, on train, its mean return is at least the baseline's mean
   return, **or** its mean max drawdown is at least 5 percentage points lower and its mean
   return falls no more than 10% below the baseline's (relative).
2. Among survivors, select the variant with the **highest mean validation return**.
3. **Accept** only if the selected variant beats the baseline's mean validation return
   **and** fires (blocks or exits) on at least 3 separate occasions across the three
   markets in train + validation. A filter that rarely triggers can't be judged.
4. Otherwise **reject**: the funding filter adds nothing, and v3 continues alone in F1.

### Holdout: forward data

Every historical period has now been looked at under v3. So v4's out-of-sample test is
**forward**: if accepted, the selected v4 variant is paper-traded alongside v3 in F1, over
the same schedule, with the same rules. Funding comes live from OKX.

- **v4 forward pass:** at the two-year verdict, v4's pooled gap (share of rises kept minus
  share of falls taken) is larger than v3's over the same weeks, and v4 passes F1's final
  verdict on its own. v4 is also subject to F1's fidelity and six-month consistency checks.
- If F1 has already started when v4 is accepted, v4's forward test starts on its own
  acceptance date and runs its own full 104 weeks.

### Disclosures

- Fourth protocol. Variants tried so far: 18 (v1) + 18 (v2) + 8 (v3) + 4 (v4).
- The v4 base rule was selected on v3's train and validation data. So v4 versus baseline
  on those segments compares two rules where the baseline already had the advantage of
  being selected there. That makes the bar harder for v4, not easier.
- v3's holdout results are known. v4 doesn't use that period for any decision.
- Funding history comes from Binance while prices come from Gate. Both are market-wide
  measures; the strategy only reads funding as a level, not as a tradable price.

### Implementation needed (after commit)

- A funding-data loader (Binance bulk files, cached locally) and a live OKX loader.
- The filter added to the trend strategy (parameters: threshold, action).
- A v4 runner: grid plus baseline on train and validation, the selection rule, and a count
  of filter triggers.
