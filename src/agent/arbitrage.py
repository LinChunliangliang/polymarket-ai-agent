import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from src.models.market import Market
from src.models.portfolio import RiskConfig, Portfolio
from src.storage import db

logger = logging.getLogger(__name__)

# Polymarket 收取约 2% 手续费（从盈利中扣除）
FEE_RATE = 0.02


@dataclass
class ArbOpportunity:
    market: Market
    yes_price: float
    no_price: float
    sum_price: float        # YES + NO
    net_profit_pct: float   # 扣除手续费后的净利润率
    bet_amount: float       # 每条腿下注金额


def find_arb_opportunities(
    markets: List[Market],
    min_profit_pct: float = 0.005,   # 最低 0.5% 净利润才执行
    min_liquidity: float = 200.0,
) -> List[ArbOpportunity]:
    """扫描 YES + NO < 1 的套利机会，返回按利润率排序的列表。"""
    opportunities = []

    for market in markets:
        yes_p = market.yes_price
        no_p = market.no_price
        total = yes_p + no_p

        # 必须严格小于 1 才有套利空间
        if total >= 1.0:
            continue

        # 流动性过滤
        if market.liquidity_usd < min_liquidity:
            continue

        # 计算扣费后净利润
        # 投入 yes_p + no_p，必然获得 $1，手续费取更差的一侧
        payout_yes_wins = 1 - FEE_RATE * (1 - yes_p)
        payout_no_wins  = 1 - FEE_RATE * (1 - no_p)
        min_payout = min(payout_yes_wins, payout_no_wins)
        net_profit = min_payout - total
        net_profit_pct = net_profit / total

        if net_profit_pct < min_profit_pct:
            continue

        opportunities.append(ArbOpportunity(
            market=market,
            yes_price=yes_p,
            no_price=no_p,
            sum_price=total,
            net_profit_pct=net_profit_pct,
            bet_amount=0.0,  # 由 compute_arb_size 填入
        ))

    opportunities.sort(key=lambda x: x.net_profit_pct, reverse=True)
    return opportunities


def compute_arb_size(
    opp: ArbOpportunity,
    portfolio: Portfolio,
    risk: RiskConfig,
) -> Optional[float]:
    """计算每条腿的下注金额，返回 None 表示跳过。"""
    # 每条腿投入相同金额，套利利润 = amount * net_profit_pct
    max_by_pct = portfolio.current_balance_usd * risk.max_position_pct
    amount = min(max_by_pct, portfolio.current_balance_usd * 0.10)  # 套利最多用 10%
    amount = round(amount, 2)

    if amount < risk.min_bet_usd:
        return None

    # 检查余额够支付两条腿
    total_cost = round(amount * (opp.yes_price + opp.no_price), 2)
    if total_cost > portfolio.current_balance_usd * 0.9:
        return None

    return amount


async def execute_arb(
    opp: ArbOpportunity,
    amount: float,
    portfolio: Portfolio,
    polymarket_client=None,
    dry_run: bool = False,
) -> bool:
    """
    执行套利：同时买 YES 和 NO。
    返回 True 表示两条腿都成交，False 表示失败/仅部分成交。
    """
    yes_cost = round(amount * opp.yes_price, 4)
    no_cost  = round(amount * opp.no_price, 4)
    total_cost = yes_cost + no_cost
    expected_profit = round(amount * opp.net_profit_pct, 4)

    logger.info(
        "ARB EXECUTE: %s YES@%.3f NO@%.3f cost=$%.2f expected_profit=$%.4f dry=%s",
        opp.market.condition_id[:20], opp.yes_price, opp.no_price,
        total_cost, expected_profit, dry_run,
    )

    if dry_run:
        logger.info("[DRY RUN] ARB would place YES $%.2f + NO $%.2f = cost $%.2f profit $%.4f",
                    yes_cost, no_cost, total_cost, expected_profit)
        return True

    if polymarket_client is None:
        logger.warning("No Polymarket client, skipping arb execution")
        return False

    # 两条腿并行提交，最大化同步成交概率
    from src.agent.executor import _submit_order
    try:
        yes_task = _submit_order(polymarket_client, opp.market, "YES", yes_cost, opp.yes_price)
        no_task  = _submit_order(polymarket_client, opp.market, "NO",  no_cost,  opp.no_price)
        yes_result, no_result = await asyncio.gather(yes_task, no_task, return_exceptions=True)

        yes_ok = not isinstance(yes_result, Exception)
        no_ok  = not isinstance(no_result, Exception)

        if yes_ok and no_ok:
            logger.info("ARB SUCCESS: both legs filled, profit=$%.4f", expected_profit)
            # 更新投资组合（成本先扣，结算时收回）
            portfolio.current_balance_usd = round(portfolio.current_balance_usd - total_cost, 4)
            db.update_portfolio(portfolio)
            return True
        else:
            # 部分成交风险：记录日志，不自动平仓（等待手动处理）
            logger.error(
                "ARB PARTIAL FILL: YES=%s NO=%s — manual review needed for %s",
                yes_ok, no_ok, opp.market.condition_id[:20],
            )
            return False

    except Exception as e:
        logger.error("ARB execution error: %s", e)
        return False
