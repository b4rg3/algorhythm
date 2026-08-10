"""Position sizing and stop-loss risk management."""

from config import Config


class RiskManager:
    """Calculates position sizes and stop-loss levels based on risk settings."""

    def __init__(self, config: Config) -> None:
        """Store the risk configuration."""
        self.config = config

    def position_size(self, balance_usdt: float, price: float) -> float:
        """Return the quantity of base currency to buy for one risked trade.

        Sizes so that a full stop-loss hit loses exactly risk_per_trade_pct of balance.
        """
        risk_amount = balance_usdt * self.config.risk_per_trade_pct
        stop_distance = price * self.config.stop_loss_pct
        quantity = risk_amount / stop_distance
        return round(quantity, 6)

    def stop_loss_price(self, entry_price: float, side: str) -> float:
        """Return the stop-loss trigger price for a given entry price and side."""
        if side == "BUY":
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)
