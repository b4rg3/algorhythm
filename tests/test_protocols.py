from research import protocol as P
from research import v3


def test_v1_v2_splits_are_ordered_and_fixed():
    sp = P.splits()
    assert sp.start < sp.validation_start < sp.holdout_start < sp.end
    assert (sp.end - sp.holdout_start).days == P.HOLDOUT_DAYS


def test_v1_v2_grid_and_neighbours():
    grid = P.grid()
    assert len(grid) == 18
    assert len({P.variant_label(v) for v in grid}) == 18
    for v in grid:
        for n in P.neighbours(v):
            assert n in grid and n != v


def test_v3_windows_share_the_untouched_holdout():
    assert v3.DATA_START < v3.TRAIN_START < v3.VALIDATION_START < v3.HOLDOUT_START < v3.HOLDOUT_END
    assert v3.HOLDOUT_START == P.splits().holdout_start
    assert v3.HOLDOUT_END == P.splits().end


def test_v3_grid_and_neighbours():
    grid = v3.grid()
    assert len(grid) == 8
    assert v3.neighbours({"sma": 50, "band": 0.0}) == [{"sma": 100, "band": 0.0}]
    assert v3.neighbours({"sma": 150, "band": 0.02}) == [{"sma": 100, "band": 0.02}, {"sma": 200, "band": 0.02}]


def test_v3_config_uses_registered_execution_rules():
    cfg = v3.config_for("ETH/USDT", {"sma": 100, "band": 0.02})
    assert (cfg.strategy, cfg.timeframe, cfg.history_exchange) == ("trend", "1d", "gate")
    assert (cfg.trend_sma_period, cfg.trend_band) == (100, 0.02)
    assert cfg.sizing_mode == "allocation" and cfg.allocation_pct == 1.0
    assert cfg.use_stop_loss is False
    assert cfg.coingecko_id == "ethereum"
