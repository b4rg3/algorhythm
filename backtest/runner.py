"""Walk-forward backtester — no lookahead, no persistence side effects.

Uses the same PaperTrader as the live bot (with persistence disabled), so fills, fees,
slippage and stop-loss handling are identical between backtest and live paper trading.
"""

import math

import pandas as pd

from config import Config
from execution.paper_trader import PaperTrader
from indicators.engine import IndicatorEngine
from risk.manager import RiskManager
from strategy.ma_rsi import MARSIStrategy


class Backtester:
    """Replays a historical OHLCV DataFrame through the live strategy and execution logic."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = IndicatorEngine(config)
        self.strategy = MARSIStrategy(config)
        self.risk_manager = RiskManager(config)

    def run(
        self,
        df: pd.DataFrame,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> dict:
        """Run the backtest and return a results dict.

        Indicators are computed over the whole of `df` (so earlier candles serve as warm-up),
        but trading only happens on candles in [start, end). This lets a held-out test
        period start with fully warmed-up indicators and no lookahead.
        """
        df = self.engine.calculate(df)
        if end is not None:
            df = df[df.index < end]
        first = 1
        if start is not None:
            first = max(1, int(df.index.searchsorted(start)))
        if first >= len(df):
            raise ValueError("No candles in the requested backtest window after indicator warm-up.")

        trader = PaperTrader(self.config, state_path=None)

        trades: list[dict] = []
        equity: list[float] = []

        for i in range(first, len(df)):
            slice_df = df.iloc[: i + 1]
            candle = slice_df.iloc[-1]
            ts = slice_df.index[-1]

            signal = self.strategy.signal(slice_df)
            trade = trader.execute(signal, candle, self.risk_manager)
            if trade is not None:
                trade["ts"] = ts
                trades.append(trade)

            equity.append(trader.portfolio_value(float(candle["close"])))

        final_price = float(df.iloc[-1]["close"])
        final_value = trader.portfolio_value(final_price)

        results = self._metrics(trades, equity, final_value, trader, final_price)
        start_price = float(df.iloc[first - 1]["close"])
        results["buy_hold_pct"] = (final_price / start_price - 1) * 100
        results["period_start"] = df.index[first]
        results["period_end"] = df.index[-1]
        results["candles"] = len(df) - first
        return results

    def _metrics(
        self,
        trades: list[dict],
        equity: list[float],
        final_value: float,
        trader: PaperTrader,
        final_price: float,
    ) -> dict:
        closed = [t for t in trades if "pnl" in t]
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]

        total_pnl = sum(t["pnl"] for t in closed)
        gross_wins = sum(t["pnl"] for t in wins)
        gross_losses = abs(sum(t["pnl"] for t in losses))

        # Max drawdown
        peak = equity[0] if equity else self.config.paper_balance_usdt
        max_dd_pct = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd

        return {
            "start_balance": self.config.paper_balance_usdt,
            "final_value": final_value,
            "total_return_pct": (final_value - self.config.paper_balance_usdt)
            / self.config.paper_balance_usdt
            * 100,
            "total_pnl": total_pnl,
            "total_fees": trader.total_fees,
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "stop_losses": sum(1 for t in closed if t["action"] == "STOP_LOSS"),
            "win_rate": len(wins) / len(closed) * 100 if closed else 0.0,
            "avg_win": gross_wins / len(wins) if wins else 0.0,
            "avg_loss": -gross_losses / len(losses) if losses else 0.0,
            "profit_factor": gross_wins / gross_losses if gross_losses > 0 else math.inf,
            "max_drawdown_pct": max_dd_pct,
            "best_trade": max((t["pnl"] for t in closed), default=0.0),
            "worst_trade": min((t["pnl"] for t in closed), default=0.0),
            "open_position": trader.position,
            "final_price": final_price,
            "trade_log": trades,
        }
