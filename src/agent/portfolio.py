import logging
from datetime import datetime

from src.models.portfolio import Portfolio
from src.models.bet import Bet
from src.storage import db

logger = logging.getLogger(__name__)


def deduct_bet(portfolio: Portfolio, bet_amount: float) -> Portfolio:
    portfolio.current_balance_usd = round(portfolio.current_balance_usd - bet_amount, 4)
    portfolio.total_wagered_usd = round(portfolio.total_wagered_usd + bet_amount, 4)
    portfolio.last_updated_at = datetime.utcnow()
    db.update_portfolio(portfolio)
    logger.debug("Deducted $%.2f. Balance: $%.2f", bet_amount, portfolio.current_balance_usd)
    return portfolio


def apply_settlement(portfolio: Portfolio, bet: Bet) -> Portfolio:
    """Apply a resolved bet's P&L to the portfolio."""
    if bet.pnl_usd is None:
        return portfolio

    portfolio.total_pnl_usd = round(portfolio.total_pnl_usd + bet.pnl_usd, 4)
    portfolio.last_updated_at = datetime.utcnow()

    if bet.pnl_usd < 0:
        portfolio.daily_loss_usd = round(portfolio.daily_loss_usd + abs(bet.pnl_usd), 4)

    # On a win, funds are returned plus profit
    if bet.pnl_usd > 0:
        portfolio.current_balance_usd = round(
            portfolio.current_balance_usd + bet.amount_usd + bet.pnl_usd, 4
        )
    # On a loss, funds were already deducted at bet time; just track the loss
    db.update_portfolio(portfolio)
    logger.info(
        "Settlement: %s pnl=$%.2f balance=$%.2f",
        bet.condition_id[:16], bet.pnl_usd, portfolio.current_balance_usd,
    )
    return portfolio


def deduct_ai_cost(portfolio: Portfolio, cost_usd: float) -> Portfolio:
    portfolio.current_balance_usd = round(portfolio.current_balance_usd - cost_usd, 6)
    portfolio.total_ai_cost_usd = round(portfolio.total_ai_cost_usd + cost_usd, 6)
    portfolio.last_updated_at = datetime.utcnow()
    db.update_portfolio(portfolio)
    return portfolio


def reset_daily_loss(portfolio: Portfolio) -> Portfolio:
    """Called at 00:00 UTC to reset daily loss counter."""
    logger.info("Resetting daily loss. Was $%.2f", portfolio.daily_loss_usd)
    portfolio.daily_loss_usd = 0.0
    portfolio.last_updated_at = datetime.utcnow()
    db.update_portfolio(portfolio)
    return portfolio
