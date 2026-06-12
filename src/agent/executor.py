import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.models.bet import Bet
from src.models.market import Market
from src.models.portfolio import Portfolio, RiskConfig
from src.storage import db
from src.agent import portfolio as port_mgr
from src.agent.risk import check_pre_bet

logger = logging.getLogger(__name__)


async def place_bet(
    market: Market,
    side: str,
    amount_usd: float,
    kelly_fraction: float,
    signal_id: int,
    portfolio: Portfolio,
    risk: RiskConfig,
    polymarket_client=None,
    dry_run: bool = False,
) -> Optional[Bet]:
    """
    Place a bet on Polymarket. Returns the created Bet or None on failure.
    In dry_run mode, logs the intent but skips actual order submission.
    """
    risk_check = check_pre_bet(portfolio, risk, amount_usd)
    if not risk_check.passed:
        logger.info("Risk check blocked bet: %s", risk_check.reason)
        return None

    price = market.yes_price if side == "YES" else market.no_price

    bet = Bet(
        id=None,
        condition_id=market.condition_id,
        signal_id=signal_id,
        side=side,
        amount_usd=amount_usd,
        price_at_order=price,
        kelly_fraction=kelly_fraction,
        order_id=None,
        status="pending",
    )
    bet_id = db.insert_bet(bet)
    bet.id = bet_id
    port_mgr.deduct_bet(portfolio, amount_usd)

    if dry_run:
        logger.info(
            "[DRY RUN] Would bet %s $%.2f on %s @ %.4f",
            side, amount_usd, market.condition_id[:20], price,
        )
        db.update_bet_status(bet_id, "cancelled")
        bet.status = "cancelled"
        return bet

    if polymarket_client is None:
        logger.warning("No Polymarket client available, skipping order")
        db.update_bet_status(bet_id, "cancelled")
        return None

    try:
        order_result = await _submit_order(polymarket_client, market, side, amount_usd, price)
        order_id = order_result.get("orderID") or order_result.get("id", "")
        db.update_bet_status(bet_id, "filled", order_id=order_id)
        bet.status = "filled"
        bet.order_id = order_id
        logger.info(
            "Bet placed: %s %s $%.2f orderID=%s",
            side, market.condition_id[:16], amount_usd, order_id,
        )
        from src.agent.notifier import notify_bet_placed
        from src.agent.main import get_config
        if get_config().notify.notify_on_bet:
            await notify_bet_placed(side, amount_usd, market.question, price)
    except Exception as e:
        logger.error("Order placement failed for %s: %s", market.condition_id, e)
        db.update_bet_status(bet_id, "cancelled")
        bet.status = "cancelled"
        # Return deducted funds
        portfolio.current_balance_usd = round(portfolio.current_balance_usd + amount_usd, 4)
        db.update_portfolio(portfolio)

    return bet


async def _submit_order(client, market: Market, side: str, amount: float, price: float) -> dict:
    """Submit order to Polymarket CLOB. Returns order response dict."""
    # polymarket-apis client usage
    from py_clob_client.order_builder.constants import BUY
    token_id = _get_token_id(market, side)
    size = round(amount / price, 4)

    order = client.create_limit_order(
        token_id=token_id,
        price=price,
        size=size,
        side=BUY,
    )
    resp = client.post_order(order)
    return resp if isinstance(resp, dict) else {"orderID": str(resp)}


def _get_token_id(market: Market, side: str) -> str:
    token_id = market.yes_token_id if side == "YES" else market.no_token_id
    if not token_id:
        raise ValueError(f"No token ID for {side} on market {market.condition_id[:20]}. "
                         "Market may not have been fetched with clobTokenIds.")
    return token_id


async def poll_settlements(polymarket_client=None) -> None:
    """Check open bets for settlement. Update portfolio on resolution."""
    from src.storage.db import get_open_bets, get_portfolio

    open_bets = get_open_bets()
    if not open_bets:
        return

    portfolio = get_portfolio()

    for bet in open_bets:
        if bet.status != "filled":
            continue
        try:
            resolved = await _check_resolution(polymarket_client, bet)
            if resolved is not None:
                won, pnl = resolved
                status = "won" if won else "lost"
                db.update_bet_status(bet.id, status, pnl_usd=pnl)
                bet.pnl_usd = pnl
                port_mgr.apply_settlement(portfolio, bet)
                logger.info("Settled bet %d: %s pnl=$%.2f", bet.id, status, pnl)
                from src.agent.notifier import notify_bet_settled
                from src.agent.main import get_config
                if get_config().notify.notify_on_settle:
                    await notify_bet_settled(bet.side, bet.amount_usd, pnl, bet.condition_id)
        except Exception as e:
            logger.debug("Settlement check error for bet %d: %s", bet.id, e)


async def _check_resolution(client, bet: Bet):
    """Returns (won: bool, pnl: float) if resolved, else None."""
    if client is None:
        return None
    try:
        await asyncio.sleep(0)  # yield
        market_data = client.get_market(bet.condition_id)
        if not market_data:
            return None
        resolved = market_data.get("resolved", False)
        if not resolved:
            return None
        result = market_data.get("result") or market_data.get("outcome")
        if result is None:
            return None
        won = (str(result).upper() == bet.side)
        if won:
            pnl = round(bet.potential_payout - bet.amount_usd, 4)
        else:
            pnl = -bet.amount_usd
        return won, pnl
    except Exception:
        return None
