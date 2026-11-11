import json

import pytest

from execution.paper_trader import PaperTrader
from risk.manager import RiskManager
from tests.conftest import candle


def trader_for(config, **kw):
    return PaperTrader(config, state_path=kw.get("state_path")), RiskManager(config)


def test_buy_fills_at_close_plus_slippage_and_pays_fee(cfg):
    t, rm = trader_for(cfg)
    trade = t.execute("BUY", candle(1.0), rm)

    fill = 1.0 * (1 + cfg.slippage_pct)
    assert trade["action"] == "BUY"
    assert trade["price"] == pytest.approx(fill)
    assert trade["fee"] == pytest.approx(trade["quantity"] * fill * cfg.fee_pct)
    # Cash spent + cash left == starting balance.
    assert t.balance_usdt + t.position["entry_cost"] == pytest.approx(1000.0)


def test_risk_sizing_targets_risk_pct_of_balance(cfg):
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    fill = 1.0 * (1 + cfg.slippage_pct)
    expected_qty = 1000 * cfg.risk_per_trade_pct / (fill * cfg.stop_loss_pct)
    assert t.position["quantity"] == pytest.approx(expected_qty, rel=1e-5)


def test_stop_triggers_on_intrabar_low_and_fills_at_stop(cfg):
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    stop = t.position["stop_loss"]

    # Wick through the stop, close back above it.
    trade = t.execute("HOLD", candle(1.0, open_=1.0, low=stop * 0.99, high=1.0), rm)
    assert trade["action"] == "STOP_LOSS"
    assert trade["price"] == pytest.approx(stop * (1 - cfg.slippage_pct))
    assert t.position is None


def test_gap_down_through_stop_fills_at_open(cfg):
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    trade = t.execute("HOLD", candle(0.88, open_=0.90, low=0.85), rm)
    assert trade["action"] == "STOP_LOSS"
    assert trade["price"] == pytest.approx(0.90 * (1 - cfg.slippage_pct))


def test_no_stop_when_low_stays_above(cfg):
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    stop = t.position["stop_loss"]
    assert t.execute("HOLD", candle(1.0, low=stop * 1.001), rm) is None
    assert t.position is not None


def test_flat_round_trip_loses_exactly_costs(cfg):
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    q = t.position["quantity"]
    trade = t.execute("SELL", candle(1.0), rm)

    s, f = cfg.slippage_pct, cfg.fee_pct
    expected = q * (1 - s) * (1 - f) - q * (1 + s) * (1 + f)
    assert trade["pnl"] == pytest.approx(expected)
    assert t.balance_usdt == pytest.approx(1000 + expected)
    assert t.total_fees == pytest.approx(q * (1 + s) * f + q * (1 - s) * f)


def test_allocation_mode_invests_whole_balance(make_config):
    cfg = make_config(sizing_mode="allocation", allocation_pct=1.0)
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(2.0), rm)
    assert 0 <= t.balance_usdt < 0.01
    assert t.position["entry_cost"] == pytest.approx(1000.0, abs=0.01)


def test_allocation_mode_partial(make_config):
    cfg = make_config(sizing_mode="allocation", allocation_pct=0.5)
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(2.0), rm)
    assert t.position["entry_cost"] == pytest.approx(500.0, abs=0.01)


def test_stop_loss_can_be_disabled(make_config):
    cfg = make_config(sizing_mode="allocation", use_stop_loss=False)
    t, rm = trader_for(cfg)
    trade = t.execute("BUY", candle(1.0), rm)
    assert trade["stop_loss"] is None
    # A 50% crash doesn't close the position without a SELL signal.
    assert t.execute("HOLD", candle(0.5, open_=0.6, low=0.4), rm) is None
    assert t.position is not None


def test_ignores_buy_while_long_and_sell_while_flat(cfg):
    t, rm = trader_for(cfg)
    assert t.execute("SELL", candle(1.0), rm) is None
    t.execute("BUY", candle(1.0), rm)
    qty = t.position["quantity"]
    assert t.execute("BUY", candle(1.0), rm) is None
    assert t.position["quantity"] == qty


def test_no_buy_with_tiny_balance(make_config):
    t, rm = trader_for(make_config(paper_balance_usdt=5.0))
    assert t.execute("BUY", candle(1.0), rm) is None


def test_state_persists_and_reloads(cfg, tmp_path):
    path = str(tmp_path / "portfolio.json")
    t, rm = trader_for(cfg, state_path=path)
    t.execute("BUY", candle(1.0), rm, candle_ts="2026-01-01 00:00:00+00:00")

    reloaded = PaperTrader(cfg, state_path=path)
    assert reloaded.position == t.position
    assert reloaded.balance_usdt == pytest.approx(t.balance_usdt)
    assert reloaded.total_fees == pytest.approx(t.total_fees)
    assert reloaded.already_processed("2026-01-01 00:00:00+00:00")
    assert not reloaded.already_processed("2026-01-01 00:15:00+00:00")


def test_legacy_state_without_entry_cost_still_closes(cfg, tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({
        "balance_usdt": 500.0,
        "balance_base": 100.0,
        "position": {"side": "BUY", "entry_price": 5.0, "quantity": 100.0, "stop_loss": 4.0},
    }))
    t = PaperTrader(cfg, state_path=str(path))
    trade = t.execute("SELL", candle(5.0), RiskManager(cfg))
    assert trade["action"] == "SELL"
    assert trade["pnl"] < 0  # costs only


def test_no_persistence_when_state_path_is_none(cfg, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    t, rm = trader_for(cfg)
    t.execute("BUY", candle(1.0), rm)
    assert list(tmp_path.iterdir()) == []
