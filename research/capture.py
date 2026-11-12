"""Weekly 'share of rises kept' vs 'share of falls taken' (see RESEARCH.md, F1).

Inputs are daily series indexed by candle open time (UTC):
  equity: the strategy's portfolio value at each candle close
  close:  the coin's close for the same candles
Both should include one reference point before the test (starting equity / last
warm-up close) so the first week has a starting value.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Capture:
    rises_kept_pct: float
    falls_taken_pct: float
    up_weeks: int
    down_weeks: int

    @property
    def gap(self) -> float:
        return self.rises_kept_pct - self.falls_taken_pct


def weekly_returns(equity: pd.Series, close: pd.Series, complete_only: bool = True) -> pd.DataFrame:
    """Weekly (Mon-Sun UTC) % returns of strategy (`s`) and coin (`b`).

    With complete_only, keeps only weeks whose 7 daily candles are all present and whose
    previous week-end value exists, i.e. calendar weeks fully inside the data.
    """
    frame = pd.concat([equity, close], axis=1, keys=["eq", "close"]).dropna()
    week_end = frame.resample("W-SUN").last()
    counts = frame["close"].resample("W-SUN").count()
    out = pd.DataFrame({
        "s": week_end["eq"].pct_change() * 100,
        "b": week_end["close"].pct_change() * 100,
        "days": counts,
    }).dropna()
    if complete_only:
        out = out[out["days"] == 7]
    return out[["s", "b"]]


def capture(weekly: pd.DataFrame) -> Capture:
    """Share of the coin's weekly rises the strategy kept, and of its falls it took."""
    up, down = weekly[weekly["b"] > 0], weekly[weekly["b"] < 0]
    kept = up["s"].sum() / up["b"].sum() * 100 if len(up) else float("nan")
    taken = down["s"].sum() / down["b"].sum() * 100 if len(down) else float("nan")
    return Capture(kept, taken, len(up), len(down))
