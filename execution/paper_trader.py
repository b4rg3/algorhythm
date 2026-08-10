"""Simulated (paper) trade execution."""

import json
import os
from typing import Optional

from config import Config
from risk.manager import RiskManager

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "portfolio.json")


class PaperTrader:
    """Simulates trade execution and tracks a paper trading portfolio."""

    def __init__(self, config: Config) -> None:
        """Initialise balances from saved state if it exists, otherwise use config defaults."""
        self.config = config
        self.balance_usdt: float = config.paper_balance_usdt
        self.balance_base: float = 0.0
        self.position: Optional[dict] = None
        self._load()

    def _load(self) -> None:
        """Restore portfolio state from disk if a saved state file exists."""
        if not os.path.exists(STATE_PATH):
            return
        with open(STATE_PATH) as f:
            state = json.load(f)
        self.balance_usdt = state["balance_usdt"]
        self.balance_base = state["balance_base"]
        self.position = state["position"]

    def _save(self) -> None:
        """Persist current portfolio state to disk."""
        with open(STATE_PATH, "w") as f:
            json.dump(
                {
                    "balance_usdt": self.balance_usdt,
                    "balance_base": self.balance_base,
                    "position": self.position,
                },
                f,
                indent=2,
            )

    def execute(self, signal: str, price: float, risk_manager: RiskManager) -> Optional[dict]:
        """Simulate executing a signal at the given price, returning a trade dict or None."""
        if self.position is not None:
            side = self.position["side"]
            stop_hit = (side == "BUY" and price <= self.position["stop_loss"]) or (
                side == "SELL" and price >= self.position["stop_loss"]
            )
            if stop_hit:
                trade = self._close_position(price, action="STOP_LOSS")
                self._save()
                return trade

        if signal == "BUY" and self.position is None and self.balance_usdt > 10:
            quantity = risk_manager.position_size(self.balance_usdt, price)
            cost = quantity * price
            if cost > self.balance_usdt:
                quantity = round(self.balance_usdt / price, 6)
                cost = quantity * price
            self.balance_usdt -= cost
            self.balance_base += quantity

            stop_loss = risk_manager.stop_loss_price(price, "BUY")
            self.position = {
                "side": "BUY",
                "entry_price": price,
                "quantity": quantity,
                "stop_loss": stop_loss,
            }
            self._save()
            return {
                "action": "BUY",
                "price": price,
                "quantity": quantity,
                "stop_loss": stop_loss,
                "balance_usdt": self.balance_usdt,
                "balance_base": self.balance_base,
            }

        if signal == "SELL" and self.position is not None:
            trade = self._close_position(price, action="SELL")
            self._save()
            return trade

        return None

    def _close_position(self, price: float, action: str) -> dict:
        """Close the open position at the given price, returning the trade dict."""
        quantity = self.balance_base
        proceeds = quantity * price
        entry_cost = self.position["quantity"] * self.position["entry_price"]

        self.balance_usdt += proceeds
        self.balance_base = 0.0
        pnl = proceeds - entry_cost
        self.position = None

        return {
            "action": action,
            "price": price,
            "quantity": quantity,
            "pnl": pnl,
            "balance_usdt": self.balance_usdt,
            "balance_base": self.balance_base,
        }

    def portfolio_value(self, price: float) -> float:
        """Return the total portfolio value in USDT at the given price."""
        return self.balance_usdt + self.balance_base * price
