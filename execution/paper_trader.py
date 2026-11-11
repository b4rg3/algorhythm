"""Simulated (paper) trade execution, shared by the live bot and the backtester."""

import json
import os
from typing import Optional

from config import Config
from risk.manager import RiskManager

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "portfolio.json")


class PaperTrader:
    """Simulates trade execution and tracks a paper trading portfolio.

    Fills are modelled conservatively:
      - BUY / SELL signals fill at the candle close, moved against us by `slippage_pct`.
      - Stop-losses trigger when the candle LOW touches the stop. They fill at the stop
        price, or at the open if the candle gapped below it, then slippage is applied.
      - Every fill pays `fee_pct` of its notional value.

    Pass `state_path=None` to disable persistence (used by the backtester).
    """

    def __init__(self, config: Config, state_path: Optional[str] = STATE_PATH) -> None:
        """Initialise balances from saved state if it exists, otherwise use config defaults."""
        self.config = config
        self.state_path = state_path
        self.balance_usdt: float = config.paper_balance_usdt
        self.balance_base: float = 0.0
        self.position: Optional[dict] = None
        self.total_fees: float = 0.0
        self.last_candle_ts: Optional[str] = None
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Restore portfolio state from disk if a saved state file exists."""
        if not self.state_path or not os.path.exists(self.state_path):
            return
        with open(self.state_path) as f:
            state = json.load(f)
        self.balance_usdt = state["balance_usdt"]
        self.balance_base = state["balance_base"]
        self.position = state["position"]
        self.total_fees = state.get("total_fees", 0.0)
        self.last_candle_ts = state.get("last_candle_ts")

    def _save(self) -> None:
        """Persist current portfolio state to disk (no-op when persistence is disabled)."""
        if not self.state_path:
            return
        with open(self.state_path, "w") as f:
            json.dump(
                {
                    "balance_usdt": self.balance_usdt,
                    "balance_base": self.balance_base,
                    "position": self.position,
                    "total_fees": self.total_fees,
                    "last_candle_ts": self.last_candle_ts,
                },
                f,
                indent=2,
            )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def already_processed(self, candle_ts) -> bool:
        """Return True if this candle has already been acted on (live-loop dedupe)."""
        return self.last_candle_ts is not None and str(candle_ts) == self.last_candle_ts

    def execute(
        self, signal: str, candle, risk_manager: RiskManager, candle_ts=None
    ) -> Optional[dict]:
        """Process one completed candle: check the stop-loss, then act on the signal.

        `candle` is any mapping with open/high/low/close (e.g. a DataFrame row).
        Returns a trade dict, or None if nothing happened.
        """
        trade = self._process(signal, candle, risk_manager)
        if candle_ts is not None:
            self.last_candle_ts = str(candle_ts)
        self._save()
        return trade

    def _process(self, signal: str, candle, risk_manager: RiskManager) -> Optional[dict]:
        open_ = float(candle["open"])
        low = float(candle["low"])
        close = float(candle["close"])

        if self.position is not None:
            stop = self.position.get("stop_loss")
            if stop is not None and low <= stop:
                trigger = min(stop, open_)  # gap-down fills at the open, not the stop
                return self._close_position(trigger, action="STOP_LOSS")

        if signal == "BUY" and self.position is None and self.balance_usdt > 10:
            return self._open_long(close, risk_manager)

        if signal == "SELL" and self.position is not None:
            return self._close_position(close, action="SELL")

        return None

    def _open_long(self, price: float, risk_manager: RiskManager) -> dict:
        fee_pct = self.config.fee_pct
        fill = price * (1 + self.config.slippage_pct)

        max_quantity = int(self.balance_usdt / (fill * (1 + fee_pct)) * 1e6) / 1e6
        if self.config.sizing_mode == "allocation":
            quantity = int(max_quantity * self.config.allocation_pct * 1e6) / 1e6
        else:
            quantity = min(risk_manager.position_size(self.balance_usdt, fill), max_quantity)

        notional = quantity * fill
        fee = notional * fee_pct
        self.balance_usdt -= notional + fee
        self.balance_base += quantity
        self.total_fees += fee

        stop_loss = risk_manager.stop_loss_price(fill, "BUY") if self.config.use_stop_loss else None
        self.position = {
            "side": "BUY",
            "entry_price": fill,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "entry_cost": notional + fee,
        }
        return {
            "action": "BUY",
            "price": fill,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "fee": fee,
            "balance_usdt": self.balance_usdt,
            "balance_base": self.balance_base,
        }

    def _close_position(self, price: float, action: str) -> dict:
        """Close the open long at `price` (before slippage), returning the trade dict."""
        fill = price * (1 - self.config.slippage_pct)
        quantity = self.balance_base
        notional = quantity * fill
        fee = notional * self.config.fee_pct
        proceeds = notional - fee

        pos = self.position
        entry_cost = pos.get("entry_cost", pos["quantity"] * pos["entry_price"])
        pnl = proceeds - entry_cost

        self.balance_usdt += proceeds
        self.balance_base = 0.0
        self.total_fees += fee
        self.position = None

        return {
            "action": action,
            "price": fill,
            "quantity": quantity,
            "fee": fee,
            "pnl": pnl,
            "balance_usdt": self.balance_usdt,
            "balance_base": self.balance_base,
        }

    def portfolio_value(self, price: float) -> float:
        """Return the total portfolio value in USDT at the given price (before exit costs)."""
        return self.balance_usdt + self.balance_base * price
