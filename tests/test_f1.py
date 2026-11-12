import json
import os

import numpy as np
import pandas as pd
import pytest

import f1 as runner
import forward_check
from research import f1
from research.capture import capture, weekly_returns
from tests.conftest import ohlcv_frame, random_walk

REGISTERED = pd.Timestamp("2026-01-01 00:05", tz="UTC")
START = f1.start_candle(REGISTERED)  # 2026-01-01 candle, closes 2026-01-02 00:00


# ---------------------------------------------------------------- capture metric

def test_capture_shares():
    weekly = pd.DataFrame({"b": [10, -10, 20, -5], "s": [6, -3, 10, -2]})
    c = capture(weekly)
    assert c.rises_kept_pct == pytest.approx(16 / 30 * 100)
    assert c.falls_taken_pct == pytest.approx(5 / 15 * 100)
    assert (c.up_weeks, c.down_weeks) == (2, 2)
    assert c.gap == pytest.approx(16 / 30 * 100 - 5 / 15 * 100)


def test_weekly_returns_keeps_only_complete_weeks():
    idx = pd.date_range("2026-01-01", "2026-01-31", freq="1D", tz="UTC")  # starts on a Thursday
    s = pd.Series(np.arange(len(idx), dtype=float) + 100, index=idx)
    w = weekly_returns(s, s)
    # Complete Mon-Sun weeks with a prior week-end: Jan 5-11, 12-18, 19-25.
    assert list(w.index.strftime("%Y-%m-%d")) == ["2026-01-11", "2026-01-18", "2026-01-25"]


def test_start_candle_rule():
    assert f1.start_candle(pd.Timestamp("2026-11-12 00:05:18", tz="UTC")) == pd.Timestamp("2026-11-12", tz="UTC")
    assert f1.start_candle(pd.Timestamp("2026-11-12 23:59", tz="UTC")) == pd.Timestamp("2026-11-12", tz="UTC")


# ---------------------------------------------------------------- runner with a fake Kraken

class FakeExchange:
    def fetch_order_book(self, symbol, limit=None):
        return {"bids": [[99.9, 1e9, 0]], "asks": [[100.1, 1e9, 0]]}


class FakeFetcher:
    """Serves a fixed daily history; only candles closed by `now` are visible."""
    data: dict = {}
    now: pd.Timestamp = None

    def __init__(self, config):
        self.config, self.exchange = config, FakeExchange()

    def fetch_candles(self, limit=100):
        df = self.data[self.config.symbol]
        return df[df.index + pd.Timedelta(days=1) <= self.now].iloc[-limit:]


@pytest.fixture
def market(tmp_path):
    # 300 warm-up days before START, then 120 test days; trending so trades happen.
    n_warm, n_test = 300, 120
    data = {}
    for i, sym in enumerate(f1.SYMBOLS):
        closes = random_walk(n_warm + n_test, seed=10 + i, vol=0.04)
        data[sym] = ohlcv_frame(closes, start=str((START - pd.Timedelta(days=n_warm)).date()))
    FakeFetcher.data = data
    return tmp_path, data


def step(base, day: pd.Timestamp, hour: int = 1):
    FakeFetcher.now = day + pd.Timedelta(hours=hour)
    return [runner.run_symbol(s, base_dir=str(base), now=FakeFetcher.now, fetcher_factory=FakeFetcher,
                              registered_at=REGISTERED) for s in f1.SYMBOLS]


def rows(base, sym):
    with open(os.path.join(f1.symbol_dir(sym, str(base)), "daily.jsonl")) as f:
        return [json.loads(l) for l in f if l.strip()]


def test_waits_until_first_candle_closes(market):
    base, _ = market
    out = step(base, START, hour=12)  # START candle hasn't closed yet
    assert all("waiting" in o for o in out)
    assert not os.path.exists(os.path.join(f1.symbol_dir(f1.SYMBOLS[0], str(base)), "daily.jsonl"))


def test_daily_processing_is_idempotent_and_counts_missed_closes(market):
    base, _ = market
    sym = f1.SYMBOLS[0]
    step(base, START + pd.Timedelta(days=1))
    step(base, START + pd.Timedelta(days=1), hour=5)  # second run same day: nothing new
    assert len(rows(base, sym)) == 1

    step(base, START + pd.Timedelta(days=4))  # offline for two closes
    r = rows(base, sym)
    assert [x["missed"] for x in r] == [False, True, True, False]
    assert r[-1]["delay_hours"] == pytest.approx(1.0)


def test_forward_check_fidelity_passes_and_catches_tampering(market):
    base, _ = market
    for d in range(1, 120):
        step(base, START + pd.Timedelta(days=d))
    result = forward_check.evaluate(base_dir=str(base), registered_at=REGISTERED)
    assert result["fidelity_ok"]
    assert sum(p["fidelity"]["trades"] for p in result["symbols"].values()) > 0
    assert result["complete_weeks"] >= 15
    assert result["interim"] is not None
    assert "checkpoint" not in result  # fewer than 26 weeks

    # Tamper with one recorded trade price: fidelity must fail.
    sym = next(s for s, p in result["symbols"].items() if p["fidelity"]["trades"])
    path = os.path.join(f1.symbol_dir(sym, str(base)), "trades.jsonl")
    trades = [json.loads(l) for l in open(path)]
    trades[0]["price"] *= 1.01
    with open(path, "w") as f:
        f.writelines(json.dumps(t) + "\n" for t in trades)
    assert not forward_check.evaluate(base_dir=str(base), registered_at=REGISTERED)["fidelity_ok"]


def test_trades_record_book_stats(market):
    base, _ = market
    for d in range(1, 60):
        step(base, START + pd.Timedelta(days=d))
    for sym in f1.SYMBOLS:
        path = os.path.join(f1.symbol_dir(sym, str(base)), "trades.jsonl")
        if os.path.exists(path):
            t = json.loads(open(path).readline())
            assert t["book"]["spread_pct"] == pytest.approx(0.2, abs=1e-6)
            return
    pytest.fail("expected at least one trade")
