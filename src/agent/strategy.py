import logging
from typing import Optional, Tuple

from src.models.signal import Signal
from src.models.market import Market
from src.models.portfolio import RiskConfig, Portfolio

logger = logging.getLogger(__name__)


def kelly_bet_size(
    prob: float,
    price: float,
    kelly_fraction: float = 0.25,
) -> float:
    """
    Calculate Kelly bet fraction.
    For a binary outcome at price p:
      b = (1/p - 1)  (net odds on a win)
      f* = (p_est * b - q) / b
    Returns fractional Kelly, floored at 0.
    """
    if price <= 0 or price >= 1:
        return 0.0
    b = (1.0 / price) - 1.0
    q = 1.0 - prob
    raw_f = (prob * b - q) / b
    if raw_f <= 0:
        return 0.0
    return raw_f * kelly_fraction


def compute_bet(
    signal: Signal,
    market: Market,
    portfolio: Portfolio,
    risk: RiskConfig,
) -> Optional[Tuple[str, float, float]]:
    """
    Returns (side, amount_usd, kelly_fraction) or None if no bet should be placed.
    """
    dev = signal.deviation
    threshold = risk.deviation_threshold

    if abs(dev) < threshold:
        logger.debug("Signal below threshold: dev=%.3f < %.3f", abs(dev), threshold)
        return None

    side = "YES" if dev > 0 else "NO"
    price = market.yes_price if side == "YES" else market.no_price

    # Apply confidence discount
    conf_multiplier = {"high": 1.0, "medium": 0.75, "low": 0.5}.get(signal.confidence, 0.75)

    raw_kelly = kelly_bet_size(signal.estimated_prob if side == "YES" else 1 - signal.estimated_prob,
                               price, risk.kelly_fraction)
    adjusted_kelly = raw_kelly * conf_multiplier

    max_bet = portfolio.current_balance_usd * risk.max_position_pct
    amount = min(adjusted_kelly * portfolio.current_balance_usd, max_bet)
    amount = round(amount, 2)

    if amount < risk.min_bet_usd:
        logger.debug("Computed bet $%.2f below minimum $%.2f", amount, risk.min_bet_usd)
        return None

    if not market.has_sufficient_liquidity(amount, risk.min_liquidity_multiple):
        logger.info(
            "Insufficient liquidity for %s: need $%.0f, have $%.0f",
            market.condition_id[:16], amount * risk.min_liquidity_multiple, market.liquidity_usd,
        )
        return None

    logger.info(
        "Bet signal: %s %s $%.2f (kelly=%.3f conf=%s dev=%+.3f)",
        side, market.condition_id[:16], amount, adjusted_kelly, signal.confidence, dev,
    )
    return side, amount, adjusted_kelly
