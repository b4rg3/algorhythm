"""Walk-forward backtester — no lookahead, no persistence side effects."""

import math

import pandas as pd

from config import Config
from indicators.engine import IndicatorEngine
from risk.manager import RiskManager
from strategy.ma_rsi import MARSIStrategy


class Backtester:
    """Replays a historical OHLCV DataFrame through the live strategy logic."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.engine = IndicatorEngine(config)
        self.strategy = MARSIStrategy(config)
        self.risk_manager = RiskManager(config)

    def run(self, df: pd.DataFrame) -> dict:
        """Run the backtest and return a results dict."""
        df = self.engine.calculate(df)

        balance_usdt: float = self.config.paper_balance_usdt
        balance_base: float = 0.0
        position: dict | None = None

        trades: list[dict] = []
        equity: list[float] = []

        for i in range(1, len(df)):
            slice_df = df.iloc[: i + 1]
            price: float = float(slice_df.iloc[-1]["close"])

            # Check stop-loss on open position
            if position is not None:
                stop_hit = price <= position["stop_loss"]
                if stop_hit:
                    proceeds = balance_base * price
                    pnl = proceeds - position["quantity"] * position["entry_price"]
                    balance_usdt += proceeds
                    balance_base = 0.0
                    trades.append({
                        "action": "STOP_LOSS",
                        "price": price,
                        "quantity": position["quantity"],
                        "pnl": pnl,
                        "ts": slice_df.index[-1],
                    })
                    position = None

            signal = self.strategy.signal(slice_df)

            if signal == "BUY" and position is None and balance_usdt > 10:
                quantity = self.risk_manager.position_size(balance_usdt, price)
                cost = quantity * price
                if cost > balance_usdt:
                    quantity = round(balance_usdt / price, 6)
                    cost = quantity * price
                balance_usdt -= cost
                balance_base += quantity
                stop_loss = self.risk_manager.stop_loss_price(price, "BUY")
                position = {
                    "side": "BUY",
                    "entry_price": price,
                    "quantity": quantity,
                    "stop_loss": stop_loss,
                }
                trades.append({
                    "action": "BUY",
                    "price": price,
                    "quantity": quantity,
                    "ts": slice_df.index[-1],
                })

            elif signal == "SELL" and position is not None:
                proceeds = balance_base * price
                pnl = proceeds - position["quantity"] * position["entry_price"]
                balance_usdt += proceeds
                balance_base = 0.0
                trades.append({
                    "action": "SELL",
                    "price": price,
                    "quantity": position["quantity"],
                    "pnl": pnl,
                    "ts": slice_df.index[-1],
                })
                position = None

            equity.append(balance_usdt + balance_base * price)

        # Close any open position at last price for reporting
        final_price = float(df.iloc[-1]["close"])
        final_value = balance_usdt + balance_base * final_price

        return self._metrics(trades, equity, final_value, position, final_price)

    def _metrics(
        self,
        trades: list[dict],
        equity: list[float],
        final_value: float,
        open_position: dict | None,
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
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed) * 100 if closed else 0.0,
            "avg_win": gross_wins / len(wins) if wins else 0.0,
            "avg_loss": -gross_losses / len(losses) if losses else 0.0,
            "profit_factor": gross_wins / gross_losses if gross_losses > 0 else math.inf,
            "max_drawdown_pct": max_dd_pct,
            "best_trade": max((t["pnl"] for t in closed), default=0.0),
            "worst_trade": min((t["pnl"] for t in closed), default=0.0),
            "open_position": open_position,
            "final_price": final_price,
            "trade_log": trades,
        }
