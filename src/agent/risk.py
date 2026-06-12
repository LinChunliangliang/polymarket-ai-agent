import logging
from dataclasses import dataclass

from src.models.portfolio import Portfolio, RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    passed: bool
    reason: str = ""


def check_pre_bet(
    portfolio: Portfolio,
    risk: RiskConfig,
    bet_amount: float,
) -> RiskCheckResult:
    """Gate check before placing any bet. Returns pass/fail with reason."""

    if portfolio.current_balance_usd < risk.min_bet_usd:
        return RiskCheckResult(False, f"Balance ${portfolio.current_balance_usd:.2f} below minimum ${risk.min_bet_usd:.2f}")

    if portfolio.daily_loss_usd >= risk.daily_loss_limit_usd:
        return RiskCheckResult(False, f"Daily loss limit reached: ${portfolio.daily_loss_usd:.2f} >= ${risk.daily_loss_limit_usd:.2f}")

    max_bet = portfolio.current_balance_usd * risk.max_position_pct
    if bet_amount > max_bet:
        return RiskCheckResult(False, f"Bet ${bet_amount:.2f} exceeds max position ${max_bet:.2f}")

    if bet_amount < risk.min_bet_usd:
        return RiskCheckResult(False, f"Bet ${bet_amount:.2f} below minimum ${risk.min_bet_usd:.2f}")

    return RiskCheckResult(True, "ok")


def check_daily_loss_limit(portfolio: Portfolio, risk: RiskConfig) -> bool:
    """Returns True if daily loss limit is reached (agent should pause)."""
    return portfolio.daily_loss_usd >= risk.daily_loss_limit_usd
