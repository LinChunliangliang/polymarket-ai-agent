import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.agent import main as app_main
from src.agent.scanner import fetch_all_markets, fetch_crypto_markets, filter_tradeable, fetch_prices
from src.agent.estimator import estimate_probability
from src.agent.strategy import compute_bet
from src.agent.executor import place_bet, poll_settlements
from src.agent import portfolio as port_mgr
from src.agent.risk import check_daily_loss_limit
from src.models.portfolio import RiskConfig
from src.storage.db import get_portfolio
from src.agent.arbitrage import find_arb_opportunities, compute_arb_size, execute_arb

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_polymarket_client = None
_risk_config: Optional[RiskConfig] = None
_dry_run: bool = False

# Cache of last AI estimates: {condition_id: yes_price_at_analysis}
_last_analysis_prices: dict = {}

# Cache of last arb scan results
_last_arb_opps: list = []
_last_arb_scanned_at: Optional[datetime] = None


def get_last_arb() -> dict:
    return {
        "opportunities": _last_arb_opps,
        "scanned_at": _last_arb_scanned_at.isoformat() if _last_arb_scanned_at else None,
    }


def setup_scheduler(risk: RiskConfig, poly_client=None, dry_run: bool = False) -> AsyncIOScheduler:
    global _scheduler, _polymarket_client, _risk_config, _dry_run
    _polymarket_client = poly_client
    _risk_config = risk
    _dry_run = dry_run

    _scheduler = AsyncIOScheduler()

    now = datetime.utcnow()

    # Fast price check every N minutes — run immediately on start
    _scheduler.add_job(
        run_price_check_cycle,
        IntervalTrigger(minutes=risk.price_check_interval_min),
        id="price_check",
        name="Price Check Cycle",
        misfire_grace_time=60,
        next_run_time=now,
    )

    # Full AI scan every N minutes — run immediately on start
    _scheduler.add_job(
        run_ai_scan_cycle,
        IntervalTrigger(minutes=risk.ai_scan_interval_min),
        id="ai_scan",
        name="AI Scan Cycle",
        misfire_grace_time=300,
        next_run_time=now,
    )

    # Arbitrage scan — runs at same cadence as price check
    _scheduler.add_job(
        run_arb_scan_cycle,
        IntervalTrigger(minutes=risk.price_check_interval_min),
        id="arb_scan",
        name="Arbitrage Scan",
        misfire_grace_time=60,
        next_run_time=now,
    )

    # Daily loss reset at 00:00 UTC
    _scheduler.add_job(
        _reset_daily_loss,
        CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="daily_reset",
        name="Daily Loss Reset",
    )

    return _scheduler


async def run_price_check_cycle() -> None:
    if app_main.should_stop():
        logger.info("Stop flag detected, halting agent.")
        if _scheduler:
            _scheduler.shutdown(wait=False)
        return

    start = datetime.utcnow()
    logger.info("price_check_cycle started")

    try:
        if not _last_analysis_prices:
            logger.debug("No previous analysis prices, skipping price delta check")
            return

        condition_ids = list(_last_analysis_prices.keys())
        current_prices = await fetch_prices(condition_ids)

        flagged = []
        for cid, old_price in _last_analysis_prices.items():
            new_price = current_prices.get(cid)
            if new_price and abs(new_price - old_price) > 0.03:
                flagged.append(cid)
                logger.debug("Price moved >3%% for %s: %.3f → %.3f", cid[:16], old_price, new_price)

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            "price_check_cycle completed | markets=%d flagged=%d duration=%.1fs",
            len(condition_ids), len(flagged), elapsed,
        )
    except Exception as e:
        logger.error("price_check_cycle error: %s", e)


async def run_ai_scan_cycle() -> None:
    if app_main.should_stop():
        return

    cfg = app_main.get_config()
    risk = _risk_config
    start = datetime.utcnow()
    logger.info("ai_scan_cycle started")

    try:
        portfolio = get_portfolio()

        if check_daily_loss_limit(portfolio, risk):
            logger.warning("Daily loss limit reached ($%.2f), skipping AI scan", portfolio.daily_loss_usd)
            from src.agent.notifier import notify_daily_loss_limit
            from src.agent.main import get_config as _get_cfg
            if _get_cfg().notify.notify_on_loss_limit:
                await notify_daily_loss_limit(portfolio.daily_loss_usd, risk.daily_loss_limit_usd)
            return

        if "all" in cfg.scanning.categories:
            markets = await fetch_all_markets(max_results=500)
        else:
            markets = await fetch_crypto_markets(
                categories=cfg.scanning.categories,
                max_results=300,
            )
        tradeable = filter_tradeable(
            markets,
            top_n=risk.max_markets_per_ai_scan,
        )

        if not tradeable:
            logger.info("ai_scan_cycle: no tradeable markets found")
            return

        signals_found = 0
        bets_placed = 0
        total_ai_cost = 0.0

        # Parallel analysis
        tasks = [
            estimate_probability(
                market=m,
                api_key=cfg.deepseek.api_key,
                model=cfg.deepseek.model,
                dry_run=_dry_run,
            )
            for m in tradeable
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for market, result in zip(tradeable, results):
            if isinstance(result, Exception) or result is None:
                continue

            signal = result
            total_ai_cost += signal.ai_cost_usd

            # Cache analysis price
            _last_analysis_prices[market.condition_id] = market.yes_price

            # Deduct AI cost from portfolio
            portfolio = port_mgr.deduct_ai_cost(portfolio, signal.ai_cost_usd)

            threshold = risk.deviation_threshold
            if abs(signal.deviation) <= threshold:
                continue

            signals_found += 1
            bet_decision = compute_bet(signal, market, portfolio, risk)
            if bet_decision is None:
                continue

            side, amount, kelly = bet_decision
            bet = await place_bet(
                market=market,
                side=side,
                amount_usd=amount,
                kelly_fraction=kelly,
                signal_id=signal.id,
                portfolio=portfolio,
                risk=risk,
                polymarket_client=_polymarket_client,
                dry_run=_dry_run,
            )
            if bet and bet.status == "filled":
                bets_placed += 1

        # Check settlements
        await poll_settlements(_polymarket_client)

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            "ai_scan_cycle completed | markets_analyzed=%d signals_found=%d bets_placed=%d ai_cost=$%.4f duration=%.1fs",
            len(tradeable), signals_found, bets_placed, total_ai_cost, elapsed,
        )
        from src.agent.notifier import notify_cycle_summary
        from src.agent.main import get_config as _get_cfg
        if _get_cfg().notify.notify_cycle_summary:
            top = [
                {"question": m.question, "yes_price": m.yes_price, "liquidity_usd": m.liquidity_usd}
                for m in tradeable[:3]
            ]
            await notify_cycle_summary(len(tradeable), signals_found, bets_placed, total_ai_cost,
                                       top_markets=top, dry_run=_dry_run)
    except Exception as e:
        logger.error("ai_scan_cycle error: %s", e, exc_info=True)
        from src.agent.notifier import notify_agent_error
        await notify_agent_error(str(e))


async def run_arb_scan_cycle() -> None:
    global _last_arb_opps, _last_arb_scanned_at
    if app_main.should_stop():
        return

    cfg = app_main.get_config()
    risk = _risk_config
    start = datetime.utcnow()
    logger.info("arb_scan_cycle started")

    try:
        portfolio = get_portfolio()

        if check_daily_loss_limit(portfolio, risk):
            logger.debug("Daily loss limit reached, skipping arb scan")
            return

        # Arb scans ALL categories — mathematical arbitrage is market-agnostic
        markets = await fetch_all_markets(max_results=500)
        all_with_prices = [m for m in markets if m.yes_price > 0 and m.no_price > 0]

        opportunities = find_arb_opportunities(
            all_with_prices,
            min_profit_pct=getattr(cfg, "arb_min_profit_pct", 0.005),
            min_liquidity=200.0,
        )

        _last_arb_scanned_at = datetime.utcnow()
        _last_arb_opps = opportunities

        if not opportunities:
            logger.info("arb_scan_cycle: no arbitrage opportunities found")
            return

        logger.info("arb_scan_cycle: found %d opportunities", len(opportunities))

        executed = 0
        for opp in opportunities[:3]:  # max 3 arb trades per cycle
            amount = compute_arb_size(opp, portfolio, risk)
            if amount is None:
                continue
            opp.bet_amount = amount
            success = await execute_arb(
                opp, amount, portfolio,
                polymarket_client=_polymarket_client,
                dry_run=_dry_run,
            )
            if success:
                executed += 1

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            "arb_scan_cycle completed | found=%d executed=%d duration=%.1fs",
            len(opportunities), executed, elapsed,
        )
        from src.agent.notifier import notify_arb_opportunity
        await notify_arb_opportunity(opportunities, executed, dry_run=_dry_run)

    except Exception as e:
        logger.error("arb_scan_cycle error: %s", e, exc_info=True)
        from src.agent.notifier import notify_agent_error
        await notify_agent_error(f"arb_scan error: {e}")


async def _reset_daily_loss() -> None:
    portfolio = get_portfolio()
    port_mgr.reset_daily_loss(portfolio)
